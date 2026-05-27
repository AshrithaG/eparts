"""M5: end-to-end evaluation on the M1 test split.

Implements V1_Engineering_Spec §5.4 + §5.5 + §7.2 M5.

Workflow:
    1. Load M3a/M3b/M4 artifacts from a run directory.
    2. Load M1 test split + the 1A ground-truth rows for those products.
    3. Run the InferencePipeline on each test product description (text
       reconstructed from 1B columns).
    4. Compute spec §5.4 metrics — overall + per-ProductType.
    5. Generate spec §5.5 artifacts (CSV + matplotlib PNGs).
    6. Persist the report bundle to ``reports/v1/<UTC_timestamp>/``.

Layer 2 is skipped during evaluation (conf_rule = 0). For an end-to-end
rule-included evaluation, an extraction-team integration test under
``tests/fixtures/extraction/`` will eventually drive a separate eval
mode; today the spec §1.3 auto-process targets at threshold 0.85 are
unreachable in semantic-only mode (max conf_final ≤ 1 − α = 0.3) and
we instead report a threshold sensitivity sweep at lower thresholds.

Usage:
    py scripts/m5_evaluate.py
    py scripts/m5_evaluate.py --max-products 500       # quick smoke
    py scripts/m5_evaluate.py --run-dir <path>
"""
from __future__ import annotations

import argparse
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")                          # type: ignore[attr-defined]
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")                          # type: ignore[attr-defined]

import numpy as np
import pandas as pd

from src.config import load_settings
from src.data import iter_attribute_pairs, load_products
from src.data.split import DEFAULT_SPLIT_DIR
from src.contracts import SourceType
from src.layer3_semantic import (
    ClusterStore,
    Encoder,
    ProductIndex,
    SemanticScorer,
    build_pt_index_from_1b,
    build_usage_prior_from_2a,
)
from src.layer4_decision import Layer4Decision, SigmaTable
from src.evaluation import (
    EvaluationReport,
    InferencePipeline,
    PerPTMetrics,
    auto_process_stats,
    brier_score,
    collect_failure_cases,
    confidence_histogram,
    confusion_matrix_counts,
    expected_calibration_error,
    latency_percentiles,
    threshold_sweep,
    top_k_accuracy,
    write_report_bundle,
)
from src.evaluation.plots import (
    confidence_histogram_plot,
    confusion_heatmap,
    latency_histogram,
    reliability_diagram,
)


REPORTS_ROOT = REPO_ROOT / "reports" / "v1"


def _build_text(row: dict, columns: tuple[str, ...]) -> str:
    parts = []
    for col in columns:
        v = row.get(col)
        if v is None:
            continue
        s = str(v).strip()
        if s and s.lower() != "nan":
            parts.append(s)
    return " ".join(parts)


def _norm(s: str) -> str:
    return " ".join(str(s or "").strip().lower().split())


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path,
                        default=REPO_ROOT / "artifacts" / "v1" / "current")
    parser.add_argument("--max-products", type=int, default=None,
                        help="Cap test products evaluated (debug / smoke).")
    parser.add_argument("--n-bins", type=int, default=10,
                        help="ECE / reliability diagram bin count.")
    args = parser.parse_args(argv)

    settings = load_settings()

    print(f"Loading M3 + M4 artifacts from {args.run_dir} ...")
    t0 = time.perf_counter()
    product_index = ProductIndex.load(args.run_dir, settings.faiss)
    print(f"  FAISS: ntotal={product_index.size:,}  ({time.perf_counter() - t0:.2f}s)")

    t0 = time.perf_counter()
    store = ClusterStore.load(args.run_dir)
    print(f"  Clusters: {len(store):,} ({store.n_low_sample:,} low-sample)  "
          f"({time.perf_counter() - t0:.1f}s)")

    t0 = time.perf_counter()
    sigma_table = SigmaTable.load(args.run_dir)
    print(f"  SigmaTable: {len(sigma_table):,} calibrated PTs  "
          f"({time.perf_counter() - t0:.2f}s)")

    print("Loading encoder ...")
    encoder = Encoder(settings.encoder)
    encoder.encode_one("warmup")
    pt_idx = build_pt_index_from_1b()
    usage_prior = build_usage_prior_from_2a()
    scorer = SemanticScorer(store, usage_prior)
    scorer.set_sigma_by_pt(sigma_table.as_sigma_by_pt())
    decider = Layer4Decision(settings.thresholds)
    pipeline = InferencePipeline(
        encoder=encoder, product_index=product_index, pt_index=pt_idx,
        scorer=scorer, decider=decider,
        model_version=str(args.run_dir.name),
    )

    print(f"Loading 1B + 1A + test split ...")
    products = load_products(
        columns=["Product_ID", "ProductType_ID", "ProductType_Name",
                 *settings.faiss.input_text_columns]
    ).set_index("Product_ID", drop=False)
    test_ids_df = pd.read_parquet(DEFAULT_SPLIT_DIR / "test.parquet", columns=["Product_ID"])
    test_ids = frozenset(int(p) for p in test_ids_df["Product_ID"])
    print(f"  test products: {len(test_ids):,}")
    if args.max_products is not None:
        rng = np.random.default_rng(42)
        test_ids = frozenset(rng.choice(list(test_ids), size=min(args.max_products, len(test_ids)),
                                        replace=False).tolist())
        print(f"  capped to {len(test_ids):,} samples")

    print("Streaming 1A for test ground-truth rows ...")
    t0 = time.perf_counter()
    truths_by_product: dict[int, list[tuple[str, str]]] = defaultdict(list)
    for chunk in iter_attribute_pairs(
        chunksize=200_000,
        columns=["Product_ID", "Attribute_Name", "Attribute_Value"],
    ):
        chunk = chunk[chunk["Product_ID"].isin(test_ids)]
        if chunk.empty:
            continue
        for pid, attr, val in zip(
            chunk["Product_ID"], chunk["Attribute_Name"], chunk["Attribute_Value"],
            strict=False,
        ):
            if pd.isna(attr) or pd.isna(val):
                continue
            truths_by_product[int(pid)].append((str(attr), str(val)))
    print(f"  collected {sum(len(v) for v in truths_by_product.values()):,} ground-truth "
          f"attribute rows across {len(truths_by_product):,} products  "
          f"({time.perf_counter() - t0:.1f}s)")

    text_cols = tuple(settings.faiss.input_text_columns)

    # ---- the evaluation loop -----------------------------------------
    print(f"\nRunning end-to-end inference on {len(truths_by_product):,} test products ...")
    t_loop = time.perf_counter()

    # Per-attribute-sample accumulators
    s_product_ids: list[int] = []
    s_pt_ids: list[int] = []
    s_pt_names: list[str] = []
    s_pt_predicted: list[int] = []
    s_attribute_names: list[str] = []
    s_true_values: list[str] = []
    s_top1_pred: list[str] = []
    s_top3_pred: list[list[str]] = []
    s_conf_embed_final: list[float] = []
    s_conf_final: list[float] = []
    s_outcomes_top1: list[int] = []

    # Per-query accumulators
    q_pt_correct: list[int] = []
    q_latency_total_ms: list[float] = []
    q_latency_phases: list[dict[str, float]] = []

    n_processed = 0
    n_skipped_blank = 0
    n_skipped_no_pt = 0
    for pid in sorted(truths_by_product.keys()):
        if pid not in products.index:
            continue
        row = products.loc[pid].to_dict()
        text = _build_text(row, text_cols)
        if not text:
            n_skipped_blank += 1
            continue
        true_pt = int(row["ProductType_ID"]) if pd.notna(row["ProductType_ID"]) else None
        out = pipeline.predict_from_text(
            text, source_type=SourceType.CSV, source_ref=f"test:{pid}",
        )
        pt_pred = out.result.product_type
        if pt_pred is None:
            n_skipped_no_pt += 1
            continue
        n_processed += 1

        q_pt_correct.append(1 if (true_pt is not None and pt_pred.product_type_id == true_pt) else 0)
        q_latency_total_ms.append(out.trace.total_ms)
        q_latency_phases.append({
            "product_id": pid,
            "encode_ms": out.trace.encode_ms,
            "search_ms": out.trace.search_ms,
            "consensus_ms": out.trace.consensus_ms,
            "score_ms": out.trace.score_ms,
            "fuse_ms": out.trace.fuse_ms,
            "total_ms": out.trace.total_ms,
        })

        # Build lookup: attribute → AttributePrediction (top-1 only).
        preds_by_attr = {p.attribute_name: p for p in out.result.predictions if p.attribute_name}
        # Top-3 candidates come from the SemanticMatcherResult that the
        # pipeline already computed — no re-encode / re-score needed.
        top3_by_attr = (
            {h.attribute_name: [c.value for c in h.top_candidates] for h in out.semantic.hits}
            if out.semantic is not None
            else {}
        )

        for attr, truth in truths_by_product[pid]:
            top1 = top3_by_attr.get(attr, [None])[0]
            top3 = top3_by_attr.get(attr, [])
            pred_record = preds_by_attr.get(attr)
            conf_embed = float(pred_record.conf_embed_final) if pred_record else 0.0
            conf_fin = float(pred_record.conf_final) if pred_record else 0.0
            s_product_ids.append(pid)
            s_pt_ids.append(true_pt if true_pt is not None else -1)
            s_pt_names.append(str(row.get("ProductType_Name") or ""))
            s_pt_predicted.append(pt_pred.product_type_id)
            s_attribute_names.append(attr)
            s_true_values.append(truth)
            s_top1_pred.append(top1 if top1 is not None else "")
            s_top3_pred.append(top3)
            s_conf_embed_final.append(conf_embed)
            s_conf_final.append(conf_fin)
            s_outcomes_top1.append(1 if (top1 is not None and _norm(top1) == _norm(truth)) else 0)

        if n_processed % 500 == 0:
            elapsed = time.perf_counter() - t_loop
            print(f"  {n_processed:>5}/{len(truths_by_product):<5}  "
                  f"running acc={sum(q_pt_correct)/max(len(q_pt_correct), 1):.4f}  "
                  f"attr_samples={len(s_product_ids):,}  "
                  f"elapsed={elapsed:.1f}s",
                  flush=True)

    loop_secs = time.perf_counter() - t_loop
    print(f"\nInference loop complete in {loop_secs:.1f}s — "
          f"{n_processed:,} products, {len(s_product_ids):,} attribute samples")
    print(f"  skipped: {n_skipped_blank:,} blank texts, {n_skipped_no_pt:,} unresolved PTs")

    if n_processed == 0:
        sys.exit("No samples evaluated — check the test split + artifacts.")

    # ---- compute metrics ---------------------------------------------
    print("Computing metrics ...")
    pt_acc = sum(q_pt_correct) / len(q_pt_correct)
    top1_overall = top_k_accuracy(s_top3_pred, s_true_values, k=1)
    top3_overall = top_k_accuracy(s_top3_pred, s_true_values, k=3)
    ece_overall = expected_calibration_error(s_conf_final, s_outcomes_top1, n_bins=args.n_bins)
    brier_overall = brier_score(s_conf_final, s_outcomes_top1)

    auto = auto_process_stats(s_conf_final, s_outcomes_top1, threshold=settings.thresholds.decision.auto_process)
    sweep = threshold_sweep(s_conf_final, s_outcomes_top1,
                            thresholds=[0.05, 0.10, 0.15, 0.20, 0.25, 0.30,
                                        settings.thresholds.decision.human_review_floor,
                                        settings.thresholds.decision.auto_process])
    lat = latency_percentiles(q_latency_total_ms)

    # Per-PT breakdown
    per_pt_buckets: dict[int, dict[str, list]] = {}
    for i, pt_id in enumerate(s_pt_ids):
        if pt_id == -1:
            continue
        b = per_pt_buckets.setdefault(pt_id, {"top1_truth": [], "top3_pred": [], "conf": [], "out": [], "name": s_pt_names[i]})
        b["top1_truth"].append(s_true_values[i])
        b["top3_pred"].append(s_top3_pred[i])
        b["conf"].append(s_conf_final[i])
        b["out"].append(s_outcomes_top1[i])

    per_pt_metrics: list[PerPTMetrics] = []
    for pt_id, b in per_pt_buckets.items():
        if not b["top1_truth"]:
            continue
        per_pt_metrics.append(PerPTMetrics(
            pt_id=pt_id, pt_name=b["name"], n_samples=len(b["top1_truth"]),
            top1_accuracy=top_k_accuracy(b["top3_pred"], b["top1_truth"], k=1),
            top3_accuracy=top_k_accuracy(b["top3_pred"], b["top1_truth"], k=3),
            ece=expected_calibration_error(b["conf"], b["out"], n_bins=args.n_bins),
            brier=brier_score(b["conf"], b["out"]),
        ))
    per_pt_metrics.sort(key=lambda m: -m.n_samples)

    # Targets met (spec §1.3 / §7.2 M5)
    targets_met = {
        "pt_accuracy_ge_0.92": pt_acc >= 0.92,
        "attribute_top1_ge_0.85": top1_overall >= 0.85,
        "attribute_top3_ge_0.95": top3_overall >= 0.95,
        "ece_le_0.05": ece_overall <= 0.05,
        "auto_process_precision_at_0.85_ge_0.95": auto.precision >= 0.95 and auto.n_auto > 0,
        "auto_process_coverage_at_0.85_ge_0.50": auto.coverage >= 0.50,
        "p50_latency_le_50ms": lat["p50"] <= 50.0,
        "p95_latency_le_200ms": lat["p95"] <= 200.0,
    }

    # ---- build report + write bundle ---------------------------------
    run_id = datetime.now(timezone.utc).strftime("run_%Y%m%d_%H%M%S")
    out_dir = REPORTS_ROOT / run_id
    print(f"\nWriting report bundle to {out_dir} ...")
    report = EvaluationReport(
        run_id=run_id, model_version=pipeline.model_version,
        n_queries_evaluated=n_processed, n_attribute_samples=len(s_product_ids),
        pt_accuracy_overall=pt_acc,
        attribute_top1_overall=top1_overall,
        attribute_top3_overall=top3_overall,
        ece_overall=ece_overall,
        brier_overall=brier_overall,
        auto_process_at_0_85=auto,
        threshold_sweep_diagnostic=sweep,
        latency_percentiles_ms=lat,
        per_pt_metrics=tuple(per_pt_metrics),
        targets_met=targets_met,
    )

    confusion = confusion_matrix_counts(
        s_attribute_names, s_top1_pred, s_true_values, top_n_attributes=10
    )
    failures = collect_failure_cases(
        product_ids=s_product_ids,
        pt_ids=s_pt_ids, pt_names=s_pt_names,
        attribute_names=s_attribute_names,
        true_values=s_true_values, predicted_values=s_top1_pred,
        confidences=s_conf_final, outcomes=s_outcomes_top1,
        top_n=20,
    )
    conf_hist = confidence_histogram(s_conf_final, n_bins=20)

    write_report_bundle(
        out_dir, report,
        confusion=confusion, failure_cases=failures,
        latency_per_query=q_latency_phases,
        confidence_histogram_bins=conf_hist,
    )

    # ---- plots --------------------------------------------------------
    print("Rendering plots ...")
    reliability_diagram(s_conf_final, s_outcomes_top1, out_dir / "reliability_overall.png",
                        title=f"Reliability — overall ({len(s_product_ids):,} samples)",
                        n_bins=args.n_bins)
    confusion_heatmap(confusion, out_dir / "confusion_top10.png")
    latency_histogram(q_latency_total_ms, out_dir / "latency_histogram.png",
                      p50_target=50.0, p95_target=200.0)
    confidence_histogram_plot(
        s_conf_final, out_dir / "confidence_distribution.png",
        auto_threshold=settings.thresholds.decision.auto_process,
        review_floor=settings.thresholds.decision.human_review_floor,
    )

    # Per-head-PT reliability diagrams (top 5 by sample count)
    for m in per_pt_metrics[:5]:
        b = per_pt_buckets[m.pt_id]
        if len(b["conf"]) < 20:
            continue
        reliability_diagram(
            b["conf"], b["out"],
            out_dir / f"reliability_pt_{m.pt_id}_{m.pt_name.replace('/', '_')[:30]}.png",
            title=f"{m.pt_name} (n={m.n_samples})",
            n_bins=args.n_bins,
        )

    # ---- summary ------------------------------------------------------
    print()
    print("=" * 70)
    print(f"M5 evaluation summary — {run_id}")
    print("=" * 70)
    print(f"  Products evaluated      : {n_processed:,}")
    print(f"  Attribute samples       : {len(s_product_ids):,}")
    print()
    print(f"  ProductType accuracy    : {pt_acc:.4f}  (target ≥ 0.92, {'PASS' if pt_acc>=0.92 else 'FAIL'})")
    print(f"  Attribute top-1         : {top1_overall:.4f}  (target ≥ 0.85, {'PASS' if top1_overall>=0.85 else 'FAIL'})")
    print(f"  Attribute top-3         : {top3_overall:.4f}  (target ≥ 0.95, {'PASS' if top3_overall>=0.95 else 'FAIL'})")
    print(f"  ECE (overall)           : {ece_overall:.4f}  (target ≤ 0.05, {'PASS' if ece_overall<=0.05 else 'FAIL'})")
    print(f"  Brier (overall)         : {brier_overall:.4f}")
    print()
    print(f"  Auto-process @ 0.85     : coverage={auto.coverage:.4f}  precision={auto.precision:.4f}")
    print(f"      target ≥ 0.50 / ≥ 0.95 — {'PASS' if (auto.coverage>=0.50 and auto.precision>=0.95) else 'FAIL'}")
    print(f"      n_auto={auto.n_auto:,}  n_correct={auto.n_correct_among_auto:,}")
    print()
    print(f"  Threshold sweep (diagnostic):")
    for s in sweep.by_threshold:
        print(f"    @ {s.threshold:.2f}  coverage={s.coverage:.4f}  precision={s.precision:.4f}  "
              f"n_auto={s.n_auto:,}")
    print()
    print(f"  Latency: p50={lat['p50']:.1f}ms (≤ 50)  p95={lat['p95']:.1f}ms (≤ 200)  "
          f"p99={lat['p99']:.1f}ms")
    print()
    print("  Targets summary:")
    for k, v in targets_met.items():
        print(f"    [{'PASS' if v else 'FAIL'}] {k}")
    print()
    print(f"Bundle written to: {out_dir}")


if __name__ == "__main__":
    main()
