"""M3b: ProductType-prediction accuracy evaluation on the train split.

Implements V1_Engineering_Spec §7.2 M3b acceptance criterion:
    "For ≥ 95% of training queries, the predicted ProductType matches the
    true ProductType."

This is a sanity check that the encoder + FAISS + consensus pipeline
makes sense on data it has seen. Real held-out accuracy lives in M5.

Workflow:
    1. Load the M3a index from the run directory (default: artifacts/v1/current/).
    2. Sample N descriptions from 1B's train split (default 2000).
    3. For each sample: encode → top-50 search → PT consensus → compare
       predicted PT to the row's true ProductType_ID.
    4. Report accuracy + a breakdown by PT_conf band.

Usage:
    py scripts/m3b_pt_accuracy_eval.py
    py scripts/m3b_pt_accuracy_eval.py --n-samples 500   # quicker run
"""
from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import numpy as np
import pandas as pd

from src.config import load_settings
from src.data import load_products
from src.data.split import DEFAULT_SPLIT_DIR
from src.layer3_semantic import (
    Encoder,
    ProductIndex,
    build_pt_index_from_1b,
    compute_pt_consensus,
)


def _build_input_text(row, columns: tuple[str, ...]) -> str:
    """Same logic as scripts/m3a_build_index.py:_build_input_text."""
    parts: list[str] = []
    for col in columns:
        value = row.get(col)
        if value is None:
            continue
        text = str(value).strip()
        if text and text.lower() != "nan":
            parts.append(text)
    return " ".join(parts)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=REPO_ROOT / "artifacts" / "v1" / "current",
    )
    parser.add_argument(
        "--n-samples", type=int, default=2000,
        help="Number of train-split products to evaluate (random sample).",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
    )
    parser.add_argument(
        "--top-k", type=int, default=None,
        help="Override FAISS top-K (default uses config/faiss.yaml top_k=50).",
    )
    args = parser.parse_args(argv)

    if not (args.run_dir / "faiss.bin").exists():
        sys.exit(f"No FAISS index at {args.run_dir}/faiss.bin.")

    settings = load_settings()

    print(f"Loading FAISS index from {args.run_dir} ...")
    product_index = ProductIndex.load(args.run_dir, settings.faiss)
    print(f"  ntotal={product_index.size:,}")

    print("Loading encoder ...")
    encoder = Encoder(settings.encoder)
    encoder.encode_one("warmup")        # force model load

    print("Loading 1B for descriptions + ground-truth PT ...")
    cols = ["Product_ID", "ProductType_ID", *settings.faiss.input_text_columns]
    products = load_products(columns=cols).set_index("Product_ID", drop=False)

    pt_idx = build_pt_index_from_1b(
        load_products(columns=["Product_ID", "ProductType_ID", "ProductType_Name"])
    )

    print(f"Loading train split from {DEFAULT_SPLIT_DIR}/train.parquet ...")
    train_ids = pd.read_parquet(DEFAULT_SPLIT_DIR / "train.parquet", columns=["Product_ID"])
    train_ids = train_ids["Product_ID"].astype(np.int64).tolist()

    # Intersect with what we actually have in 1B (and skip blanks).
    rng = np.random.default_rng(args.seed)
    train_ids_in_catalog = [pid for pid in train_ids if pid in products.index]
    sample = rng.choice(
        train_ids_in_catalog,
        size=min(args.n_samples, len(train_ids_in_catalog)),
        replace=False,
    )

    text_cols = tuple(settings.faiss.input_text_columns)
    n_correct = 0
    n_evaluated = 0
    n_blank = 0
    bands = Counter()           # 'high' / 'normal' / 'ambiguous'
    correct_by_band = Counter()

    print(f"Evaluating PT accuracy over {len(sample):,} train samples ...")
    t0 = time.perf_counter()
    for i, pid in enumerate(sample):
        row = products.loc[int(pid)]
        text = _build_input_text(row.to_dict(), text_cols)
        if not text:
            n_blank += 1
            continue
        q_vec = encoder.encode_one(text)
        [hits] = product_index.search(q_vec, k=args.top_k)
        pred = compute_pt_consensus(hits, pt_idx)
        if pred is None:
            continue
        true_pt = int(row["ProductType_ID"])
        n_evaluated += 1
        is_correct = pred.product_type_id == true_pt
        if is_correct:
            n_correct += 1

        # Band
        if pred.pt_conf >= settings.thresholds.product_type_consensus.band_high:
            band = "high (≥ 0.80)"
        elif pred.pt_conf >= settings.thresholds.product_type_consensus.band_low:
            band = "normal [0.60, 0.80)"
        else:
            band = "ambiguous (< 0.60)"
        bands[band] += 1
        if is_correct:
            correct_by_band[band] += 1

        if (i + 1) % 200 == 0:
            print(
                f"  {i + 1:>5}/{len(sample):<5}  "
                f"running acc={n_correct / max(n_evaluated, 1):.4f}  "
                f"elapsed={time.perf_counter() - t0:.1f}s",
                flush=True,
            )

    elapsed = time.perf_counter() - t0
    if n_evaluated == 0:
        sys.exit("No samples could be evaluated — check the index and splits.")
    accuracy = n_correct / n_evaluated

    print()
    print("=" * 60)
    print("PT accuracy report")
    print("=" * 60)
    print(f"  samples drawn       : {len(sample):,}")
    print(f"  blank descriptions  : {n_blank:,} (skipped)")
    print(f"  evaluated           : {n_evaluated:,}")
    print(f"  correct             : {n_correct:,}")
    print(f"  overall accuracy    : {accuracy:.4f}")
    print(f"  spec target (M3b)   : 0.9500")
    print(f"  result              : {'PASS' if accuracy >= 0.95 else 'FAIL'}")
    print(f"  wall time           : {elapsed:.1f}s ({n_evaluated / max(elapsed, 1e-6):.1f} queries/s)")
    print()
    print("Breakdown by PT_conf band:")
    for band in (
        "high (≥ 0.80)",
        "normal [0.60, 0.80)",
        "ambiguous (< 0.60)",
    ):
        n = bands.get(band, 0)
        c = correct_by_band.get(band, 0)
        share = n / max(n_evaluated, 1)
        band_acc = c / n if n else 0.0
        print(
            f"  {band:<24}  n={n:>5,}  share={share:>5.1%}  "
            f"acc={band_acc:.4f}"
        )


if __name__ == "__main__":
    main()
