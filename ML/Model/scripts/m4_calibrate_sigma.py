"""M4: per-ProductType σ calibration on the M1 validation split.

Implements V1_Engineering_Spec §5.3.

Workflow:
    1. Load the M3a FAISS run directory (default: artifacts/v1/current/).
       Rehydrate embeddings from the index without re-encoding.
    2. Load the M3b ClusterStore (centroids.parquet + cluster_cov.npz).
    3. Load 1B for the Product_ID → ProductType_ID map.
    4. Load the M1 val split product IDs.
    5. Stream 1A, filter to val-split rows, build :class:`ValQuery` records
       (one per (product, attribute, true_value) triple).
    6. Run :class:`SigmaCalibrator` per PT — caches d² once per (query,
       cluster) and replays exp() + Brier + ECE for each of the
       configured σ candidates.
    7. Persist :class:`SigmaTable` to ``sigma_table.parquet`` next to
       the FAISS index, and update ``current/`` alias.

Usage:
    py scripts/m4_calibrate_sigma.py                            # full val split
    py scripts/m4_calibrate_sigma.py --max-samples-per-pt 100   # quicker run
    py scripts/m4_calibrate_sigma.py --run-dir <path>           # specific run
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

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")                       # type: ignore[attr-defined]
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")                       # type: ignore[attr-defined]

import numpy as np
import pandas as pd

from src.config import load_settings
from src.data import iter_attribute_pairs, load_products
from src.data.split import DEFAULT_SPLIT_DIR
from src.layer3_semantic import (
    ClusterStore,
    ProductIndex,
    build_pt_index_from_1b,
    build_usage_prior_from_2a,
    rehydrate_embeddings,
)
from src.layer4_decision import SigmaCalibrator, SigmaTable, ValQuery


def _load_val_product_ids(split_dir: Path) -> frozenset[int]:
    val_path = split_dir / "val.parquet"
    if not val_path.exists():
        sys.exit(
            f"M1 val split not found at {val_path}. "
            "Run `py scripts/m1_build_splits.py` first."
        )
    df = pd.read_parquet(val_path, columns=["Product_ID"])
    return frozenset(int(p) for p in df["Product_ID"])


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=REPO_ROOT / "artifacts" / "v1" / "current",
        help="Run dir containing faiss.bin + ids.npy + centroids.parquet + cluster_cov.npz.",
    )
    parser.add_argument(
        "--max-samples-per-pt",
        type=int,
        default=None,
        help="Cap val queries per ProductType (debug / smoke). Default: no cap.",
    )
    parser.add_argument(
        "--chunksize",
        type=int,
        default=200_000,
        help="1A streaming chunk size.",
    )
    args = parser.parse_args(argv)

    settings = load_settings()
    grid = list(settings.calibration.sigma_grid)
    print(f"Sigma grid (from config/calibration.yaml): {grid}")
    print(f"Lambda_cal: {settings.calibration.lambda_cal}  reliability_bins: {settings.calibration.reliability_bins}")

    # ---- artifact load -----------------------------------------------
    print(f"\nLoading FAISS index from {args.run_dir} ...")
    t0 = time.perf_counter()
    product_index = ProductIndex.load(args.run_dir, settings.faiss)
    print(f"  ntotal={product_index.size:,}  (loaded in {time.perf_counter() - t0:.2f}s)")

    print("Rehydrating embeddings (no re-encode) ...")
    t0 = time.perf_counter()
    embeddings = rehydrate_embeddings(product_index._index)            # noqa: SLF001
    print(f"  {embeddings.shape[0]:,} × {embeddings.shape[1]}-d  ({time.perf_counter() - t0:.1f}s)")
    pid_to_row = {int(pid): i for i, pid in enumerate(product_index.product_ids)}

    print("Loading cluster store (centroids.parquet + cluster_cov.npz) ...")
    t0 = time.perf_counter()
    store = ClusterStore.load(args.run_dir)
    print(
        f"  {len(store):,} clusters ({store.n_low_sample:,} low-sample)  "
        f"({time.perf_counter() - t0:.1f}s)"
    )

    print("Loading 1B → PT map + 2A usage prior ...")
    pt_idx_obj = build_pt_index_from_1b(
        load_products(columns=["Product_ID", "ProductType_ID", "ProductType_Name"])
    )
    pt_by_product = pt_idx_obj.pt_id_by_product
    usage_prior = build_usage_prior_from_2a()
    print(f"  1B → PT: {pt_idx_obj.size:,} products")

    print(f"Loading val split from {DEFAULT_SPLIT_DIR}/val.parquet ...")
    val_ids = _load_val_product_ids(DEFAULT_SPLIT_DIR)
    print(f"  val products: {len(val_ids):,}")

    # ---- build ValQuery list -----------------------------------------
    print(f"\nStreaming 1A in chunks of {args.chunksize:,} rows, filtering to val ...")
    t0 = time.perf_counter()
    per_pt_count: Counter[int] = Counter()
    queries: list[ValQuery] = []
    n_chunks = 0
    n_kept_total = 0
    for chunk in iter_attribute_pairs(
        chunksize=args.chunksize,
        columns=["Product_ID", "Attribute_Name", "Attribute_Value"],
    ):
        n_chunks += 1
        chunk = chunk[chunk["Product_ID"].isin(val_ids)]
        if chunk.empty:
            continue
        for pid, attr, val in zip(
            chunk["Product_ID"], chunk["Attribute_Name"], chunk["Attribute_Value"],
            strict=False,
        ):
            if pd.isna(attr) or pd.isna(val):
                continue
            pid_i = int(pid)
            row_idx = pid_to_row.get(pid_i)
            if row_idx is None:
                continue
            pt_id = pt_by_product.get(pid_i)
            if pt_id is None:
                continue
            if args.max_samples_per_pt is not None and per_pt_count[pt_id] >= args.max_samples_per_pt:
                continue
            queries.append(
                ValQuery(
                    pt_id=int(pt_id),
                    product_id=pid_i,
                    query_vector=embeddings[row_idx],
                    attribute_name=str(attr),
                    true_value=str(val),
                )
            )
            per_pt_count[pt_id] += 1
            n_kept_total += 1
        print(
            f"  chunk {n_chunks:>3}: queries={n_kept_total:,} so far  "
            f"elapsed={time.perf_counter() - t0:.1f}s",
            flush=True,
        )
    print(f"  built {len(queries):,} ValQuery records across {len(per_pt_count):,} distinct PTs")
    print(f"  median samples/PT: {int(np.median(list(per_pt_count.values()))):,}")
    print(f"  max samples/PT:    {max(per_pt_count.values()):,}")

    # ---- σ grid search -----------------------------------------------
    print("\nFitting per-PT σ via grid search ...")
    t_fit = time.perf_counter()
    calibrator = SigmaCalibrator(store, usage_prior, settings.calibration)
    table = calibrator.fit(queries)
    fit_secs = time.perf_counter() - t_fit
    print(f"  fit complete in {fit_secs:.1f}s → {len(table):,} PTs calibrated")

    # ---- persist ------------------------------------------------------
    print(f"\nPersisting to {args.run_dir} ...")
    t0 = time.perf_counter()
    table.save(args.run_dir)
    print(
        f"  sigma_table.parquet: {(args.run_dir / SigmaTable.PARQUET_NAME).stat().st_size / 1024:.1f} KB  "
        f"({time.perf_counter() - t0:.2f}s)"
    )

    # ---- distribution summary -----------------------------------------
    sigma_values = [e.sigma_optimal for e in table.entries]
    bins = Counter(sigma_values)
    print("\nσ distribution across PTs:")
    for sigma in sorted(bins.keys()):
        n = bins[sigma]
        pct = n / len(table) * 100
        bar = "█" * int(round(pct / 2))
        print(f"  σ = {sigma:>6.2f}  : {n:>4} PTs ({pct:>4.1f}%) {bar}")

    print("\nBrier / ECE distribution at chosen σ:")
    briers = np.asarray([e.brier_at_opt for e in table.entries])
    eces = np.asarray([e.ece_at_opt for e in table.entries])
    print(f"  Brier  min={briers.min():.4f}  median={np.median(briers):.4f}  max={briers.max():.4f}")
    print(f"  ECE    min={eces.min():.4f}  median={np.median(eces):.4f}  max={eces.max():.4f}")


if __name__ == "__main__":
    main()
