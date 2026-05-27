"""Layer 2 Tier 1 — part-number exact match.

Implements V1_Engineering_Spec §4.2 Tier 1.

Builds a single compiled regex union from the ``Product_Number`` column of
``1B_Product_Master.csv`` (~198 K patterns) and exposes a fast lookup. The
compiled pattern is optionally cached to disk as a pickle so service
startups skip the compile step.

Performance contract from §7.2 M2 acceptance criteria:
    * Compile in < 5 s at startup.
    * Single-query latency < 1 ms after warmup.

A match is terminal — the rule engine emits a Tier-1 :class:`RuleHit` with
``conf_rule = 1.0`` and skips Layer 3 entirely (spec §4.5 special case).
"""

from __future__ import annotations

import pickle
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


@dataclass(frozen=True, slots=True)
class PartNumberMatch:
    """One Tier-1 hit on a single :class:`~src.contracts.ExtractedInput`."""

    part_number: str
    span: tuple[int, int]    # offsets within the searched text
    source: str              # "structured_field" | "free_text"


class PartNumberIndex:
    """Compiled-regex union over an arbitrary list of part numbers.

    The index is built by passing the raw list of part-number strings to
    the constructor — :func:`build_from_1b` is the production factory.
    Tests typically build small lists directly.
    """

    def __init__(self, part_numbers: Sequence[str]) -> None:
        cleaned = sorted({p.strip() for p in part_numbers if p and p.strip()})
        self._patterns: tuple[str, ...] = tuple(cleaned)
        if not cleaned:
            # Match-nothing pattern keeps the API uniform.
            self._regex: re.Pattern[str] = re.compile(r"(?!)")
        else:
            alternation = "|".join(re.escape(p) for p in cleaned)
            self._regex = re.compile(rf"(?<![A-Za-z0-9])({alternation})(?![A-Za-z0-9])")

    @property
    def size(self) -> int:
        return len(self._patterns)

    def find(self, text: str) -> PartNumberMatch | None:
        """Return the *first* part-number match in ``text``, or ``None``.

        The regex's alternation order is lexicographic over the input list,
        which is deterministic. Callers needing a specific resolution policy
        (e.g. longest match, prefer-structured-field) should orchestrate
        across :meth:`find` and the structured-field lookup explicitly.
        """
        if not text:
            return None
        m = self._regex.search(text)
        if m is None:
            return None
        return PartNumberMatch(part_number=m.group(1), span=m.span(1), source="free_text")

    def is_exact(self, candidate: str) -> bool:
        """Return ``True`` iff the cleaned candidate equals a known part number."""
        if not candidate:
            return False
        key = candidate.strip()
        # Binary search on the sorted tuple keeps this O(log N).
        from bisect import bisect_left
        i = bisect_left(self._patterns, key)
        return i < len(self._patterns) and self._patterns[i] == key

    # -- persistence ----------------------------------------------------

    def save(self, path: Path) -> None:
        """Pickle the underlying list to ``path`` so the next startup can rebuild quickly.

        We persist the *list*, not the compiled regex, because compiled
        ``re.Pattern`` objects do not pickle cleanly across Python versions.
        Recompilation from the list is the bottleneck the cache addresses.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as fh:
            pickle.dump(self._patterns, fh, protocol=pickle.HIGHEST_PROTOCOL)

    @classmethod
    def load(cls, path: Path) -> PartNumberIndex:
        with path.open("rb") as fh:
            patterns = pickle.load(fh)
        return cls(patterns)


# ---------------------------------------------------------------------------
# Production factory — build from 1B_Product_Master.csv
# ---------------------------------------------------------------------------


def build_from_1b(
    product_numbers: Iterable[str] | None = None,
    cache_path: Path | None = None,
) -> PartNumberIndex:
    """Build a :class:`PartNumberIndex` from the 1B product master.

    Args:
        product_numbers: Pre-loaded iterable of part numbers. When ``None``
            the function loads them via :func:`src.data.load_products`.
        cache_path: When provided, the resulting index's underlying list is
            pickled to ``cache_path``. Subsequent runs can call
            :meth:`PartNumberIndex.load` to skip the CSV read.

    Returns:
        A fully built :class:`PartNumberIndex`.
    """
    if product_numbers is None:
        from ..data import load_products
        df = load_products(columns=["Product_Number"])
        product_numbers = (str(v) for v in df["Product_Number"].dropna().tolist())

    idx = PartNumberIndex(list(product_numbers))
    if cache_path is not None:
        idx.save(cache_path)
    return idx
