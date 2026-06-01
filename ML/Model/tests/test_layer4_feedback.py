"""Layer 4 online-update tests (M6) — V1 spec §4.4 feedback loop + §7.2 M6.

Covers:
  * confirm math: μ_new = (N·μ_old + q)/(N+1), N += 1  (FROZEN §10.7)
  * pushback math: μ_corrected = μ_old − λ·(q − μ_old)  (FROZEN §10.7)
  * audit log: one JSONL record per update, round-trips
  * replay: audit log reapplied on top of a snapshot recovers state
  * concurrency: many updates from threads don't corrupt cluster state
  * snapshot persistence round-trip
"""
from __future__ import annotations

import threading

import numpy as np
import pytest

from src.layer3_semantic.clusters import ClusterStats, ClusterStore
from src.layer4_decision.feedback import (
    AUDIT_LOG_NAME,
    ClusterNotFoundError,
    FeedbackEvent,
    FeedbackStore,
    apply_confirm,
    apply_pushback,
)

DIM = 8
LAMBDA = 0.01


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _cluster(cid: int, pt: int, attr: str, value: str, mu: np.ndarray, n: int = 10,
             low_sample: bool = False) -> ClusterStats:
    return ClusterStats(
        cluster_id=cid,
        product_type_id=pt,
        product_type_name=f"PT{pt}",
        attribute_name=attr,
        value=value,
        n=n,
        mu=mu.astype(np.float32),
        sigma_inv=None if low_sample else np.eye(DIM, dtype=np.float32),
        log_det_sigma=0.0,
        low_sample=low_sample,
    )


@pytest.fixture
def store() -> ClusterStore:
    return ClusterStore(
        [
            _cluster(0, 10, "INPUT_VOLTAGE", "24", np.zeros(DIM, dtype=np.float32), n=10),
            _cluster(1, 10, "INPUT_VOLTAGE", "120", np.ones(DIM, dtype=np.float32), n=4, low_sample=True),
            _cluster(2, 20, "MOUNTING", "STRAP-ON", np.full(DIM, 0.5, dtype=np.float32), n=7),
        ]
    )


@pytest.fixture
def feedback(store, tmp_path) -> FeedbackStore:
    return FeedbackStore(store, artifact_dir=tmp_path, pushback_lambda=LAMBDA)


# ===========================================================================
# Pure math (FROZEN §10.7)
# ===========================================================================


def test_apply_confirm_matches_spec_formula():
    mu_old = np.array([2.0, 4.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)
    c = _cluster(0, 10, "A", "v", mu_old, n=3)
    q = np.array([6.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)
    updated = apply_confirm(c, q)
    # μ_new = (3·μ_old + q)/4 = ([6,12,..] + [6,0,..])/4 = [3, 3, 0...]
    expected = (3 * mu_old + q) / 4
    np.testing.assert_allclose(updated.mu, expected, atol=1e-6)
    assert updated.n == 4


def test_apply_confirm_preserves_low_sample_flag():
    c = _cluster(1, 10, "A", "v", np.ones(DIM, dtype=np.float32), n=4, low_sample=True)
    updated = apply_confirm(c, np.zeros(DIM, dtype=np.float32))
    # n goes 4 → 5 but cluster is NOT promoted online (Σ rebuild is offline).
    assert updated.n == 5
    assert updated.low_sample is True
    assert updated.sigma_inv is None


def test_apply_pushback_matches_spec_formula():
    mu_old = np.array([1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)
    c = _cluster(0, 10, "A", "v", mu_old, n=10)
    q = np.array([5.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)
    updated = apply_pushback(c, q, LAMBDA)
    # μ_corrected = μ_old − 0.01·(q − μ_old) = [1,1,..] − 0.01·[4,0,..] = [0.96, 1, ..]
    expected = mu_old - LAMBDA * (q - mu_old)
    np.testing.assert_allclose(updated.mu, expected, atol=1e-6)


def test_apply_pushback_does_not_change_n():
    c = _cluster(0, 10, "A", "v", np.zeros(DIM, dtype=np.float32), n=10)
    updated = apply_pushback(c, np.ones(DIM, dtype=np.float32), LAMBDA)
    assert updated.n == 10        # pushback claims no new member


# ===========================================================================
# FeedbackStore.confirm — spec §7.2 M6 "update μ and N without restart"
# ===========================================================================


def test_confirm_updates_store_in_place(feedback):
    q = np.array([4.0] + [0.0] * (DIM - 1), dtype=np.float32)
    updated = feedback.confirm(10, "INPUT_VOLTAGE", "24", q, reviewer_id="alice")
    # μ_old=0, n=10 → μ_new = (10·0 + q)/11 = q/11
    np.testing.assert_allclose(updated.mu, q / 11, atol=1e-6)
    assert updated.n == 11
    # The live store reflects it immediately — no reload.
    live = feedback.cluster_store.lookup(10, "INPUT_VOLTAGE", "24")
    assert live.n == 11
    np.testing.assert_allclose(live.mu, q / 11, atol=1e-6)


def test_confirm_unknown_cluster_raises(feedback):
    with pytest.raises(ClusterNotFoundError):
        feedback.confirm(10, "INPUT_VOLTAGE", "999", np.zeros(DIM, dtype=np.float32), reviewer_id="x")


def test_repeated_confirms_accumulate(feedback):
    q = np.ones(DIM, dtype=np.float32)
    for _ in range(5):
        feedback.confirm(20, "MOUNTING", "STRAP-ON", q, reviewer_id="bob")
    live = feedback.cluster_store.lookup(20, "MOUNTING", "STRAP-ON")
    assert live.n == 7 + 5        # started at 7


# ===========================================================================
# FeedbackStore.correct — pushback + confirm together
# ===========================================================================


def test_correct_applies_pushback_and_confirm(feedback):
    q = np.array([2.0] + [0.0] * (DIM - 1), dtype=np.float32)
    wrong_before = feedback.cluster_store.lookup(10, "INPUT_VOLTAGE", "24")
    true_before = feedback.cluster_store.lookup(10, "INPUT_VOLTAGE", "120")
    corrected_wrong, confirmed_true = feedback.correct(
        10, "INPUT_VOLTAGE", value_wrong="24", value_true="120", q=q, reviewer_id="carol"
    )
    # wrong: pushback, n unchanged
    np.testing.assert_allclose(
        corrected_wrong.mu, wrong_before.mu - LAMBDA * (q - wrong_before.mu), atol=1e-6
    )
    assert corrected_wrong.n == wrong_before.n
    # true: confirm, n += 1
    np.testing.assert_allclose(
        confirmed_true.mu, (true_before.n * true_before.mu + q) / (true_before.n + 1), atol=1e-6
    )
    assert confirmed_true.n == true_before.n + 1


def test_correct_missing_either_cluster_raises_without_mutating(feedback):
    q = np.zeros(DIM, dtype=np.float32)
    before = feedback.cluster_store.lookup(10, "INPUT_VOLTAGE", "24")
    with pytest.raises(ClusterNotFoundError):
        feedback.correct(10, "INPUT_VOLTAGE", value_wrong="24", value_true="DOES_NOT_EXIST",
                         q=q, reviewer_id="x")
    # The valid cluster must NOT have been mutated (both checked before applying).
    after = feedback.cluster_store.lookup(10, "INPUT_VOLTAGE", "24")
    assert after.n == before.n
    np.testing.assert_array_equal(after.mu, before.mu)


# ===========================================================================
# Audit log — spec §7.2 M6 "audit log entry written for every update"
# ===========================================================================


def test_confirm_writes_one_audit_line(feedback, tmp_path):
    feedback.confirm(10, "INPUT_VOLTAGE", "24", np.zeros(DIM, dtype=np.float32),
                     reviewer_id="alice", ts="2026-05-27T00:00:00+00:00")
    audit = tmp_path / AUDIT_LOG_NAME
    assert audit.exists()
    lines = audit.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    ev = FeedbackEvent.from_json_line(lines[0])
    assert ev.action == "confirm"
    assert ev.reviewer_id == "alice"
    assert ev.product_type_id == 10
    assert ev.attribute_name == "INPUT_VOLTAGE"
    assert ev.value == "24"
    assert ev.ts == "2026-05-27T00:00:00+00:00"
    assert ev.q.shape == (DIM,)


def test_correct_writes_audit_line_with_both_values_and_lambda(feedback, tmp_path):
    feedback.correct(10, "INPUT_VOLTAGE", value_wrong="24", value_true="120",
                     q=np.ones(DIM, dtype=np.float32), reviewer_id="dave")
    lines = (tmp_path / AUDIT_LOG_NAME).read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    ev = FeedbackEvent.from_json_line(lines[0])
    assert ev.action == "correct"
    assert ev.value_wrong == "24"
    assert ev.value_true == "120"
    assert ev.lambda_pushback == pytest.approx(LAMBDA)


def test_audit_event_round_trips_through_json():
    ev = FeedbackEvent(
        ts="2026-05-27T12:00:00+00:00",
        reviewer_id="erin",
        action="confirm",
        product_type_id=42,
        attribute_name="SIZE",
        q=np.array([0.1, 0.2, 0.3], dtype=np.float32),
        value="1IN",
    )
    restored = FeedbackEvent.from_json_line(ev.to_json_line())
    assert restored.reviewer_id == "erin"
    assert restored.value == "1IN"
    np.testing.assert_allclose(restored.q, ev.q, atol=1e-6)


def test_every_update_appends_exactly_one_line(feedback, tmp_path):
    feedback.confirm(10, "INPUT_VOLTAGE", "24", np.zeros(DIM, dtype=np.float32), reviewer_id="a")
    feedback.confirm(20, "MOUNTING", "STRAP-ON", np.zeros(DIM, dtype=np.float32), reviewer_id="b")
    feedback.correct(10, "INPUT_VOLTAGE", value_wrong="24", value_true="120",
                     q=np.zeros(DIM, dtype=np.float32), reviewer_id="c")
    lines = (tmp_path / AUDIT_LOG_NAME).read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3


# ===========================================================================
# Replay — recover post-snapshot updates from the audit log
# ===========================================================================


def test_replay_reapplies_confirms_on_fresh_store(store, tmp_path):
    # Session 1: apply two confirms, which append to the audit log.
    fb1 = FeedbackStore(store, artifact_dir=tmp_path, pushback_lambda=LAMBDA)
    q = np.array([4.0] + [0.0] * (DIM - 1), dtype=np.float32)
    fb1.confirm(10, "INPUT_VOLTAGE", "24", q, reviewer_id="a")
    fb1.confirm(10, "INPUT_VOLTAGE", "24", q, reviewer_id="a")
    expected = fb1.cluster_store.lookup(10, "INPUT_VOLTAGE", "24")

    # Session 2: a FRESH store (as if reloaded from the pre-update snapshot)
    # replays the audit log and must reach the same state.
    fresh = ClusterStore(
        [
            _cluster(0, 10, "INPUT_VOLTAGE", "24", np.zeros(DIM, dtype=np.float32), n=10),
            _cluster(1, 10, "INPUT_VOLTAGE", "120", np.ones(DIM, dtype=np.float32), n=4, low_sample=True),
            _cluster(2, 20, "MOUNTING", "STRAP-ON", np.full(DIM, 0.5, dtype=np.float32), n=7),
        ]
    )
    fb2 = FeedbackStore(fresh, artifact_dir=tmp_path, pushback_lambda=LAMBDA)
    n_applied = fb2.replay()
    assert n_applied == 2
    recovered = fb2.cluster_store.lookup(10, "INPUT_VOLTAGE", "24")
    assert recovered.n == expected.n
    np.testing.assert_allclose(recovered.mu, expected.mu, atol=1e-6)


def test_replay_empty_log_returns_zero(store, tmp_path):
    fb = FeedbackStore(store, artifact_dir=tmp_path, pushback_lambda=LAMBDA)
    assert fb.replay() == 0


def test_replay_skips_unknown_cluster(store, tmp_path):
    fb = FeedbackStore(store, artifact_dir=tmp_path, pushback_lambda=LAMBDA)
    fb.confirm(10, "INPUT_VOLTAGE", "24", np.zeros(DIM, dtype=np.float32), reviewer_id="a")
    # Build a fresh store MISSING that cluster; replay should skip, not crash.
    partial = ClusterStore([_cluster(2, 20, "MOUNTING", "STRAP-ON", np.zeros(DIM, dtype=np.float32))])
    fb2 = FeedbackStore(partial, artifact_dir=tmp_path, pushback_lambda=LAMBDA)
    assert fb2.replay() == 0       # the one confirm referenced a missing cluster


# ===========================================================================
# Snapshot persistence round-trip
# ===========================================================================


def test_snapshot_round_trip(feedback, tmp_path):
    q = np.ones(DIM, dtype=np.float32)
    feedback.confirm(20, "MOUNTING", "STRAP-ON", q, reviewer_id="a")
    snap_path = feedback.snapshot()
    assert snap_path.exists()
    reloaded = ClusterStore.load(tmp_path)
    live = feedback.cluster_store.lookup(20, "MOUNTING", "STRAP-ON")
    reloaded_c = reloaded.lookup(20, "MOUNTING", "STRAP-ON")
    assert reloaded_c.n == live.n
    np.testing.assert_allclose(reloaded_c.mu, live.mu, atol=1e-5)


# ===========================================================================
# Concurrency — spec §7.2 M6 "concurrent updates do not corrupt cluster state"
# ===========================================================================


def test_concurrent_confirms_do_not_lose_updates(store, tmp_path):
    fb = FeedbackStore(store, artifact_dir=tmp_path, pushback_lambda=LAMBDA)
    q = np.ones(DIM, dtype=np.float32)
    n_threads = 8
    per_thread = 5

    def worker():
        for _ in range(per_thread):
            fb.confirm(20, "MOUNTING", "STRAP-ON", q, reviewer_id="t")

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Every update must be recorded in the audit log — none lost.
    lines = (tmp_path / AUDIT_LOG_NAME).read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == n_threads * per_thread
    # And the live n reflects every confirm (started at 7).
    live = fb.cluster_store.lookup(20, "MOUNTING", "STRAP-ON")
    assert live.n == 7 + n_threads * per_thread
