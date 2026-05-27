"""Layer 2 Tier 2 — manufacturer fuzzy match.

Implements V1_Engineering_Spec §4.2 Tier 2.

Uses ``rapidfuzz.fuzz.token_set_ratio`` against the distinct manufacturer
names from ``1B_Product_Master.csv``. A score at or above
``rule_engine.manufacturer_fuzzy_min_score`` (default 90, see
:mod:`config/thresholds.yaml`) emits a single :class:`ManufacturerMatch`
with the canonical manufacturer name.

The spec scopes Tier 2 to the ``Manufacturer`` attribute only — Tier 2
never speaks for any other attribute.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from rapidfuzz import fuzz, process


@dataclass(frozen=True, slots=True)
class ManufacturerMatch:
    """A Tier-2 hit: best-scoring manufacturer at or above threshold."""

    canonical_name: str
    score: float


class ManufacturerIndex:
    """rapidfuzz-backed fuzzy lookup over a closed list of manufacturer names."""

    def __init__(self, manufacturer_names: Sequence[str]) -> None:
        cleaned = sorted({n.strip() for n in manufacturer_names if n and n.strip()})
        self._names: tuple[str, ...] = tuple(cleaned)

    @property
    def size(self) -> int:
        return len(self._names)

    @property
    def names(self) -> tuple[str, ...]:
        return self._names

    def best_match(
        self,
        candidate: str,
        min_score: int,
    ) -> ManufacturerMatch | None:
        """Return the highest-scoring manufacturer for ``candidate``.

        Args:
            candidate: The string under inspection (e.g. value of
                ``structured_fields["manufacturer_name"]``).
            min_score: Minimum ``token_set_ratio`` to accept. Below this
                Tier 2 yields ``None`` and the engine falls through.

        Returns:
            :class:`ManufacturerMatch` when a name scores ``>= min_score``,
            else ``None``. Tie-breaking is rapidfuzz's default (first by score,
            then by source ordering).
        """
        if not candidate or not self._names:
            return None
        # Case-insensitive lookup: lower-case both query and choices so
        # "johnson controls" matches "Johnson Controls" at 100.
        result = process.extractOne(
            candidate,
            self._names,
            scorer=fuzz.token_set_ratio,
            processor=lambda s: s.lower(),
            score_cutoff=min_score,
        )
        if result is None:
            return None
        match_name, score, _index = result
        return ManufacturerMatch(canonical_name=match_name, score=float(score))


# ---------------------------------------------------------------------------
# Production factory
# ---------------------------------------------------------------------------


def build_from_1b(manufacturer_names: Sequence[str] | None = None) -> ManufacturerIndex:
    """Build :class:`ManufacturerIndex` from 1B's distinct manufacturer names.

    Args:
        manufacturer_names: Pre-loaded distinct names. When ``None`` the
            function loads them via :func:`src.data.load_products`.
    """
    if manufacturer_names is None:
        from ..data import load_products
        df = load_products(columns=["Manufacturer_Name"])
        manufacturer_names = sorted(
            n for n in df["Manufacturer_Name"].dropna().unique().tolist() if str(n).strip()
        )
    return ManufacturerIndex(list(manufacturer_names))
