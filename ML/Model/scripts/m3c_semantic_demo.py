"""M3c: end-to-end Layer 3 semantic-matcher demo on real artifacts.

Wires together everything M3a/M3b/M3c built:

    text  →  Encoder       (M3a)
          →  FAISS search   (M3a)
          →  PT consensus   (M3b)
          →  per-attribute  (M3b clusters)
          →  per-value scoring with usage prior  (M3c)

For each demo query, prints:
    * Predicted ProductType + PT_conf band
    * Per attribute: top-3 candidate values with conf_embed_final,
      raw conf_embed, Mahalanobis d², usage_count, and low-sample flag

Usage:
    py scripts/m3c_semantic_demo.py
    py scripts/m3c_semantic_demo.py --query "24V damper actuator"
    py scripts/m3c_semantic_demo.py --top-k-attrs 5    # show 5 attributes/query

Sigma defaults to 1.0 (M4 will calibrate per-PT). Use --sigma to experiment.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Windows console can be non-UTF-8; force UTF-8 to be safe.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")                   # type: ignore[attr-defined]

from src.config import load_settings
from src.layer3_semantic import (
    ClusterStore,
    Encoder,
    ProductIndex,
    SemanticScorer,
    SemanticScorerConfig,
    build_pt_index_from_1b,
    build_usage_prior_from_2a,
    compute_pt_consensus,
)


DEFAULT_QUERIES = [
    "24V damper actuator with 0-10V control signal",
    "strap-on temperature sensor with 10K thermistor",
    "differential pressure transmitter for HVAC ducts",
    "NEMA 3R enclosure 32 inch wide",          # exercises the formerly-broken cluster
]


def _band(pt_conf: float, low: float, high: float) -> str:
    if pt_conf >= high:
        return f"HIGH (>= {high:.2f})"
    if pt_conf >= low:
        return f"NORMAL [{low:.2f}, {high:.2f})"
    return f"AMBIGUOUS (< {low:.2f})"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", action="append")
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=REPO_ROOT / "artifacts" / "v1" / "current",
    )
    parser.add_argument(
        "--top-k-attrs",
        type=int,
        default=None,
        help="Show only the first N attributes per query (default: all).",
    )
    parser.add_argument(
        "--sigma",
        type=float,
        default=None,
        help="Override default sigma (calibration placeholder until M4).",
    )
    args = parser.parse_args(argv)

    settings = load_settings()
    band_low = settings.thresholds.product_type_consensus.band_low
    band_high = settings.thresholds.product_type_consensus.band_high

    # ---------- artifact load ------------------------------------------
    print(f"Loading FAISS index from {args.run_dir} ...")
    t0 = time.perf_counter()
    product_index = ProductIndex.load(args.run_dir, settings.faiss)
    print(f"  ntotal={product_index.size:,}  (loaded in {time.perf_counter() - t0:.2f}s)")

    print("Loading cluster store ...")
    t0 = time.perf_counter()
    store = ClusterStore.load(args.run_dir)
    print(
        f"  {len(store):,} clusters ({store.n_low_sample:,} low-sample)  "
        f"(loaded in {time.perf_counter() - t0:.1f}s)"
    )

    print("Loading encoder + 1B + 2A ...")
    encoder = Encoder(settings.encoder)
    encoder.encode_one("warmup")                 # force model load
    pt_index = build_pt_index_from_1b()
    usage_prior = build_usage_prior_from_2a()
    print(f"  1B → PT index: {pt_index.size:,} products; 2A usage prior built")

    cfg = SemanticScorerConfig(
        default_sigma=args.sigma if args.sigma is not None else 1.0,
    )
    scorer = SemanticScorer(store, usage_prior, config=cfg)

    queries = args.query if args.query else DEFAULT_QUERIES

    # ---------- run ----------------------------------------------------
    for q_text in queries:
        print()
        print("=" * 78)
        print(f"QUERY: {q_text!r}")
        print("=" * 78)

        t_enc = time.perf_counter()
        q_vec = encoder.encode_one(q_text)
        enc_ms = (time.perf_counter() - t_enc) * 1000

        t_search = time.perf_counter()
        [hits] = product_index.search(q_vec)
        search_ms = (time.perf_counter() - t_search) * 1000

        t_consensus = time.perf_counter()
        pt_pred = compute_pt_consensus(hits, pt_index)
        consensus_ms = (time.perf_counter() - t_consensus) * 1000

        if pt_pred is None:
            print("  (no resolvable PT consensus — skipping)")
            continue

        t_score = time.perf_counter()
        result = scorer.score(q_vec, pt_pred)
        score_ms = (time.perf_counter() - t_score) * 1000

        total_ms = enc_ms + search_ms + consensus_ms + score_ms
        print(
            f"  Predicted PT : {pt_pred.product_type_name!r} (id={pt_pred.product_type_id})  "
            f"pt_conf={pt_pred.pt_conf:.3f}  band={_band(pt_pred.pt_conf, band_low, band_high)}"
        )
        print(
            f"  Latency      : encode={enc_ms:.1f}ms  search={search_ms:.2f}ms  "
            f"consensus={consensus_ms:.2f}ms  score={score_ms:.2f}ms  total={total_ms:.1f}ms"
        )
        print(
            f"  Attributes   : {len(result.hits)} found for PT  (sigma={scorer.sigma_for(pt_pred.product_type_id):.2f})"
        )

        attrs_to_show = result.hits
        if args.top_k_attrs is not None:
            attrs_to_show = result.hits[: args.top_k_attrs]
        for hit in attrs_to_show:
            print(f"  · {hit.attribute_name}")
            for rank, cand in enumerate(hit.top_candidates, start=1):
                flag = " [LOW_SAMPLE]" if cand.low_sample else ""
                print(
                    f"      {rank}. value={cand.value!r:<28.28} "
                    f"conf_final={cand.conf_embed_final:.4f}  "
                    f"conf_embed={cand.conf_embed:.4f}  "
                    f"d²={cand.mahalanobis_d2:>9.2f}  "
                    f"N={cand.cluster_n:>3}  UC={cand.usage_count:>5}{flag}"
                )


if __name__ == "__main__":
    main()
