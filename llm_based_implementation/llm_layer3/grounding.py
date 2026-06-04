"""Retrieval stub + grounding-pack assembly.

This module is the L0 + L1 piece of the plan, scoped to a fixture
catalog so the POC runs without depending on the stat track's FAISS
artifacts. When the stat track's FAISS index is wired in, the only
function that needs to change is `retrieve_top_k_stub` — the grounding
builder downstream of it is backend-agnostic.

The fixture format is small and deliberate:

  catalog.json                — list of products with attribute values
  product_type_attributes.json — PT -> list of in-scope attribute names
  canonical_values.json       — attribute -> {values: {value: usage_count}}
  scenarios.json              — list of demo queries (with expected PT)
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .schemas import AttributeSpec, GroundingPack, NeighborDigest

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


# ---------------------------------------------------------------------------
# Fixture loading
# ---------------------------------------------------------------------------

def load_fixtures(fixture_dir: str | Path) -> dict[str, Any]:
    """Load the four fixture JSON files into a single dict.

    Returns ``{"catalog": ..., "pta": ..., "canonical": ..., "scenarios": ...}``.
    """
    p = Path(fixture_dir)
    out: dict[str, Any] = {}
    out["catalog"] = json.loads((p / "catalog.json").read_text(encoding="utf-8"))
    out["pta"] = json.loads((p / "product_type_attributes.json").read_text(encoding="utf-8"))
    out["canonical"] = json.loads((p / "canonical_values.json").read_text(encoding="utf-8"))
    out["scenarios"] = json.loads((p / "scenarios.json").read_text(encoding="utf-8"))
    return out


# ---------------------------------------------------------------------------
# Retrieval — STUB
# ---------------------------------------------------------------------------

def retrieve_top_k_stub(
    query: str,
    catalog: list[dict[str, Any]],
    k: int = 5,
) -> list[NeighborDigest]:
    """Toy retrieval over the fixture catalog.

    This is intentionally NOT the real retrieval. The stat track's
    bge-small + FAISS IVFFlat index is the L0 substrate the plan
    points at; once available, swap this function for a call into
    that service. The grounding builder below is unchanged.

    The stub uses simple token overlap on (short_description +
    extended_description + product_type). Adequate for a 10-product
    fixture catalog and the four demo scenarios; not for anything
    larger.
    """
    q_tokens = set(_TOKEN_RE.findall(query.lower()))
    if not q_tokens:
        return []

    scored: list[tuple[float, dict[str, Any]]] = []
    for item in catalog:
        text = " ".join([
            item.get("short_description", ""),
            item.get("extended_description", ""),
            item.get("product_type", ""),
        ]).lower()
        item_tokens = set(_TOKEN_RE.findall(text))
        if not item_tokens:
            continue
        # Symmetric Jaccard-ish similarity, with a small boost when the
        # query directly mentions the product type.
        overlap = len(q_tokens & item_tokens)
        pt_tokens = set(_TOKEN_RE.findall(item.get("product_type", "").lower()))
        pt_boost = 0.5 if q_tokens & pt_tokens else 0.0
        denom = max(len(q_tokens | item_tokens), 1)
        score = (overlap / denom) + pt_boost
        scored.append((score, item))

    # Drop zero-overlap "padding" — a real FAISS top-K returns items
    # that all have meaningful similarity; we want the grounding pack
    # to reflect that, not be polluted by junk.
    scored = [s for s in scored if s[0] > 0.0]
    scored.sort(key=lambda x: -x[0])
    top = scored[: k]
    max_score = top[0][0] if top else 1.0
    norm = max_score if max_score > 0 else 1.0
    return [
        NeighborDigest(
            product_id=item["product_id"],
            short_description=item["short_description"],
            product_type=item["product_type"],
            similarity=min(1.0, score / norm),
            values=item.get("attributes", {}),
        )
        for score, item in top
    ]


# ---------------------------------------------------------------------------
# Grounding-pack assembly
# ---------------------------------------------------------------------------

def build_grounding_pack(
    query: str,
    neighbors: list[NeighborDigest],
    product_type_attributes: dict[str, list[str]],
    canonical_values: dict[str, dict[str, Any]],
) -> GroundingPack:
    """Deterministic assembly of the grounding pack.

    Same inputs → same pack, byte-for-byte. This is the property the
    `grounding_hash` in Provenance relies on.

    Scoping: candidate product types are the *distinct* PTs among the
    top-K neighbors (preserving order so the highest-similarity PT
    is first). In-scope attributes are the union of attributes valid
    for any candidate PT — we do not pre-commit to a single PT here,
    because that is precisely the decision the LLM is being asked to
    make. Layer-4-side caps (PT_conf < 0.60 → 0.75) still apply once
    the confidence ensemble (L3) is wired in.
    """
    seen: set[str] = set()
    candidate_pts: list[str] = []
    for n in neighbors:
        if n.product_type not in seen:
            seen.add(n.product_type)
            candidate_pts.append(n.product_type)

    attr_names: list[str] = []
    attr_seen: set[str] = set()
    for pt in candidate_pts:
        for a in product_type_attributes.get(pt, []):
            if a not in attr_seen:
                attr_seen.add(a)
                attr_names.append(a)

    in_scope: list[AttributeSpec] = []
    for name in attr_names:
        entry = canonical_values.get(name, {})
        values_dict: dict[str, int] = entry.get("values", {})
        in_scope.append(
            AttributeSpec(
                name=name,
                allowed_values=list(values_dict.keys()),
                usage_counts=dict(values_dict),
            )
        )

    return GroundingPack(
        query=query,
        top_k_neighbors=neighbors,
        candidate_product_types=candidate_pts,
        in_scope_attributes=in_scope,
    )
