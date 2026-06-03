"""Layer 4 — online incremental updates (M6).

Implements V1_Engineering_Spec §4.4 "Feedback loop" + §10.7 (FROZEN math
per §6.1).

Two per-cluster operations, applied the moment a reviewer acts:

    # Reviewer CONFIRMS value v for attribute A on query embedding q:
    μ_new = (N · μ_old + q) / (N + 1)
    N    := N + 1

    # Reviewer CORRECTS a confidently-wrong prediction (v_wrong → v_true):
    μ_{PT,A,v_wrong} := μ_old − λ · (q − μ_old),   λ = 0.01
    # ... and ALSO apply the confirm-update on (PT, A, v_true)

Design (per the M6 brief — choices A/A/A):

* **Persistence = append-only JSONL audit log + on-demand snapshot.**
  Every confirm/correct appends one line to ``feedback_audit.jsonl``
  immediately (< 1 ms, crash-safe). The in-memory :class:`ClusterStore`
  reflects the change at once. The big ``centroids.parquet`` is NOT
  rewritten per update — it is regenerated explicitly via
  :meth:`FeedbackStore.snapshot` (CLI ``snapshot`` subcommand) or
  rebuilt from a fresh M3b run. On startup, :meth:`FeedbackStore.replay`
  reapplies the audit log on top of the last snapshot so no confirmed
  update is ever lost.

* **Concurrency = ``filelock``.** A single cross-platform advisory lock
  guards both the audit-log append and the in-memory mutation, so two
  reviewers updating different clusters never interleave a torn write.

* **Σ is NOT touched here.** Per spec, Σ⁻¹ is rebuilt offline on a daily
  cadence; online updates move μ and N only. A μ shift invalidates the
  stored Σ⁻¹ slightly, which is accepted between daily rebuilds.

Audit-log record schema (one JSON object per line):

    {"ts": "<ISO8601>", "reviewer_id": "<str>", "action": "confirm|correct",
     "product_type_id": <int>, "attribute_name": "<str>",
     "value": "<str>",                 # confirm: the confirmed value
     "value_wrong": "<str>",           # correct: the wrong value (pushback target)
     "value_true": "<str>",            # correct: the true value (confirm target)
     "q": [<float>, ...],              # the query embedding (D floats)
     "lambda_pushback": <float>}       # correct only; echoes the frozen λ
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import numpy as np
from filelock import FileLock

from ..layer3_semantic.clusters import ClusterStats, ClusterStore


AUDIT_LOG_NAME = "feedback_audit.jsonl"
LOCK_NAME = "feedback.lock"


# ---------------------------------------------------------------------------
# Audit record
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FeedbackEvent:
    """One reviewer action, as stored in the audit log."""

    ts: str
    reviewer_id: str
    action: str                     # "confirm" | "correct"
    product_type_id: int
    attribute_name: str
    q: np.ndarray                   # (D,) float32 query embedding
    value: str | None = None        # confirm target
    value_wrong: str | None = None  # correct: pushback target
    value_true: str | None = None   # correct: confirm target
    lambda_pushback: float | None = None

    def to_json_line(self) -> str:
        payload: dict = {
            "ts": self.ts,
            "reviewer_id": self.reviewer_id,
            "action": self.action,
            "product_type_id": int(self.product_type_id),
            "attribute_name": self.attribute_name,
            "q": [float(x) for x in self.q],
        }
        if self.value is not None:
            payload["value"] = self.value
        if self.value_wrong is not None:
            payload["value_wrong"] = self.value_wrong
        if self.value_true is not None:
            payload["value_true"] = self.value_true
        if self.lambda_pushback is not None:
            payload["lambda_pushback"] = float(self.lambda_pushback)
        return json.dumps(payload, separators=(",", ":"))

    @classmethod
    def from_json_line(cls, line: str) -> FeedbackEvent:
        d = json.loads(line)
        return cls(
            ts=d["ts"],
            reviewer_id=d["reviewer_id"],
            action=d["action"],
            product_type_id=int(d["product_type_id"]),
            attribute_name=d["attribute_name"],
            q=np.asarray(d["q"], dtype=np.float32),
            value=d.get("value"),
            value_wrong=d.get("value_wrong"),
            value_true=d.get("value_true"),
            lambda_pushback=d.get("lambda_pushback"),
        )


# ---------------------------------------------------------------------------
# Pure cluster-math helpers (no I/O — directly unit-testable, FROZEN per §6.1)
# ---------------------------------------------------------------------------


def apply_confirm(cluster: ClusterStats, q: np.ndarray) -> ClusterStats:
    """Return a new :class:`ClusterStats` after a confirm update.

    ``μ_new = (N · μ_old + q) / (N + 1)``; ``N := N + 1``.

    Works for low-sample clusters too: their ``sigma_inv`` stays ``None``
    (Σ is a daily-rebuild concern). A confirm that pushes ``n`` to or past
    the min-size threshold does NOT promote the cluster here — promotion
    requires the offline Σ rebuild, so ``low_sample`` is preserved until
    then.
    """
    q = np.asarray(q, dtype=np.float32)
    n_old = cluster.n
    mu_new = (n_old * cluster.mu + q) / (n_old + 1)
    return replace(cluster, mu=mu_new.astype(np.float32), n=n_old + 1)


def apply_pushback(cluster: ClusterStats, q: np.ndarray, lambda_: float) -> ClusterStats:
    """Return a new :class:`ClusterStats` after error pushback.

    ``μ_corrected = μ_old − λ · (q − μ_old)``. Does NOT change ``n`` —
    pushback nudges the centroid away from a confidently-wrong query
    without claiming a new member.
    """
    q = np.asarray(q, dtype=np.float32)
    mu_new = cluster.mu - lambda_ * (q - cluster.mu)
    return replace(cluster, mu=mu_new.astype(np.float32))


# ---------------------------------------------------------------------------
# FeedbackStore — orchestrates audit log + in-memory mutation under a lock
# ---------------------------------------------------------------------------


class ClusterNotFoundError(KeyError):
    """Raised when a feedback target (PT, attribute, value) has no cluster."""


class FeedbackStore:
    """Apply reviewer feedback to a live :class:`ClusterStore`.

    The store mutates the in-memory :class:`ClusterStore` immediately and
    appends an audit record. It never rewrites ``centroids.parquet`` per
    update — call :meth:`snapshot` to persist the current state.
    """

    def __init__(
        self,
        cluster_store: ClusterStore,
        artifact_dir: Path,
        pushback_lambda: float,
    ) -> None:
        self._store = cluster_store
        self._dir = Path(artifact_dir)
        self._lambda = float(pushback_lambda)
        self._audit_path = self._dir / AUDIT_LOG_NAME
        self._lock = FileLock(str(self._dir / LOCK_NAME))

    @property
    def cluster_store(self) -> ClusterStore:
        return self._store

    @property
    def audit_path(self) -> Path:
        return self._audit_path

    # -- timestamp injection point (overridable in tests) ----------------

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    # -- public operations ----------------------------------------------

    def confirm(
        self,
        product_type_id: int,
        attribute_name: str,
        value: str,
        q: np.ndarray,
        reviewer_id: str,
        ts: str | None = None,
    ) -> ClusterStats:
        """Apply a confirm update for ``(PT, attribute, value)``.

        Raises:
            ClusterNotFoundError: if the cluster is unknown.
        """
        with self._lock:
            cluster = self._require(product_type_id, attribute_name, value)
            updated = apply_confirm(cluster, q)
            self._replace_in_store(updated)
            event = FeedbackEvent(
                ts=ts or self._now_iso(),
                reviewer_id=reviewer_id,
                action="confirm",
                product_type_id=product_type_id,
                attribute_name=attribute_name,
                value=value,
                q=np.asarray(q, dtype=np.float32),
            )
            self._append_audit(event)
            return updated

    def correct(
        self,
        product_type_id: int,
        attribute_name: str,
        value_wrong: str,
        value_true: str,
        q: np.ndarray,
        reviewer_id: str,
        ts: str | None = None,
    ) -> tuple[ClusterStats, ClusterStats]:
        """Apply a correction: pushback on ``value_wrong`` + confirm on ``value_true``.

        Returns the ``(corrected_wrong_cluster, confirmed_true_cluster)``.

        Raises:
            ClusterNotFoundError: if EITHER cluster is unknown. Neither
                mutation is applied if one is missing (checked first).
        """
        with self._lock:
            wrong = self._require(product_type_id, attribute_name, value_wrong)
            true = self._require(product_type_id, attribute_name, value_true)

            corrected_wrong = apply_pushback(wrong, q, self._lambda)
            confirmed_true = apply_confirm(true, q)
            self._replace_in_store(corrected_wrong)
            self._replace_in_store(confirmed_true)

            event = FeedbackEvent(
                ts=ts or self._now_iso(),
                reviewer_id=reviewer_id,
                action="correct",
                product_type_id=product_type_id,
                attribute_name=attribute_name,
                value_wrong=value_wrong,
                value_true=value_true,
                q=np.asarray(q, dtype=np.float32),
                lambda_pushback=self._lambda,
            )
            self._append_audit(event)
            return corrected_wrong, confirmed_true

    # -- persistence -----------------------------------------------------

    def snapshot(self) -> Path:
        """Persist the current in-memory store to ``centroids.parquet``.

        The snapshot bakes every applied update into ``centroids.parquet``.
        To keep ``load(snapshot) + replay(live_log)`` drift-free, the audit
        log is **rotated** here: the current log (whose events are now baked
        into the snapshot) is moved to a numbered archive, and a fresh empty
        live log starts. Without rotation, a restart would re-apply the
        baked-in events on top of the snapshot and ``N`` would drift upward
        (double-counting).

        Rotation **archives**, never deletes — the full audit trail is
        retained across ``feedback_audit.archived_NNN.jsonl`` files, as
        spec §7.2 M6 requires ("audit log entry written for every update").
        """
        with self._lock:
            self._store.save(self._dir)
            if self._audit_path.exists() and self._audit_path.stat().st_size > 0:
                self._audit_path.rename(self._next_archive_path())
        return self._dir / "centroids.parquet"

    def _next_archive_path(self) -> Path:
        """Next unused ``feedback_audit.archived_NNN.jsonl`` path."""
        i = 1
        while True:
            candidate = self._dir / f"feedback_audit.archived_{i:03d}.jsonl"
            if not candidate.exists():
                return candidate
            i += 1

    def replay(self) -> int:
        """Reapply the audit log on top of the current in-memory store.

        Use at service startup, after loading ``centroids.parquet``, to
        recover any confirmed updates that post-date the last snapshot.

        Returns:
            The number of audit events successfully replayed. Events that
            reference an unknown cluster are skipped (logged count only).
        """
        if not self._audit_path.exists():
            return 0
        applied = 0
        for event in self._iter_audit():
            try:
                if event.action == "confirm":
                    cluster = self._require(
                        event.product_type_id, event.attribute_name, event.value
                    )
                    self._replace_in_store(apply_confirm(cluster, event.q))
                elif event.action == "correct":
                    wrong = self._require(
                        event.product_type_id, event.attribute_name, event.value_wrong
                    )
                    true = self._require(
                        event.product_type_id, event.attribute_name, event.value_true
                    )
                    lam = event.lambda_pushback if event.lambda_pushback is not None else self._lambda
                    self._replace_in_store(apply_pushback(wrong, event.q, lam))
                    self._replace_in_store(apply_confirm(true, event.q))
                else:
                    continue
                applied += 1
            except ClusterNotFoundError:
                # Cluster vanished between snapshot and replay (e.g. a
                # rebuild dropped it). Skip; the audit line is preserved.
                continue
        return applied

    def iter_audit(self) -> Iterator[FeedbackEvent]:
        """Public iterator over the audit log (read-only)."""
        yield from self._iter_audit()

    # -- internals -------------------------------------------------------

    def _require(self, pt_id: int, attr: str, value: str) -> ClusterStats:
        cluster = self._store.lookup(pt_id, attr, value)
        if cluster is None:
            raise ClusterNotFoundError(
                f"no cluster for (pt={pt_id}, attr={attr!r}, value={value!r})"
            )
        return cluster

    def _replace_in_store(self, updated: ClusterStats) -> None:
        """Swap a cluster in the in-memory store by cluster_id, rebuilding indices."""
        new_stats = [
            updated if s.cluster_id == updated.cluster_id else s
            for s in self._store.stats
        ]
        # ClusterStore rebuilds its lookup dicts in __init__.
        self._store = ClusterStore(new_stats)

    def _append_audit(self, event: FeedbackEvent) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        with self._audit_path.open("a", encoding="utf-8") as fh:
            fh.write(event.to_json_line() + "\n")

    def _iter_audit(self) -> Iterator[FeedbackEvent]:
        if not self._audit_path.exists():
            return
        with self._audit_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    yield FeedbackEvent.from_json_line(line)
