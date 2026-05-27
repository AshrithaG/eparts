"""M3b: build per-cluster centroids + covariance from 1A train split.

Implements V1_Engineering_Spec §4.3 [3d] + §5.2 reference index build.

Workflow:
    1. Load the M3a FAISS run directory (default: artifacts/v1/current/).
    2. Rehydrate the 384-d embeddings out of the FAISS index without
       re-encoding (uses ``index.reconstruct_n``).
    3. Build the Product_ID → (ProductType_ID, ProductType_Name) map from 1B.
    4. Load the M1 train split product-ID set (data/splits/train.parquet).
    5. Stream 1A in 200K-row chunks, keep only train-split rows, group
       embeddings by (ProductType_ID, Attribute_Name, Attribute_Value),
       and compute μ + Ledoit-Wolf Σ per group.
    6. Persist as ``centroids.parquet`` + ``cluster_cov.npz`` next to the
       FAISS index in the same run directory.

Usage:
    py scripts/m3b_build_clusters.py                       # full build
    py scripts/m3b_build_clusters.py --chunk-limit 5       # quick smoke (5 1A chunks ≈ 1M rows)
    py scripts/m3b_build_clusters.py --run-dir <path>      # target a specific run
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Force UTF-8 stdout so non-ASCII characters in build output don't crash the
# build on Windows consoles that default to GBK / CP1252.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")               # type: ignore[attr-defined]
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")               # type: ignore[attr-defined]

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import numpy as np
import pandas as pd

from src.config import load_settings
from src.data import iter_attribute_pairs, load_products
from src.data.split import DEFAULT_SPLIT_DIR
from src.layer3_semantic import (
    ProductIndex,
    build_clusters,
    build_pt_index_from_1b,
    rehydrate_embeddings,
)


def _load_train_product_ids(split_dir: Path) -> frozenset[int]:
    """Read M1's train split → set of int64 Product_IDs."""
    train_path = split_dir / "train.parquet"
    if not train_path.exists():
        sys.exit(
            f"M1 train split not found at {train_path}. "
            "Run `py scripts/m1_build_splits.py` first."
        )
    df = pd.read_parquet(train_path, columns=["Product_ID"])
    return frozenset(int(p) for p in df["Product_ID"])


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=REPO_ROOT / "artifacts" / "v1" / "current",
        help="Run directory containing the M3a faiss.bin + ids.npy.",
    )
    parser.add_argument(
        "--chunk-limit",
        type=int,
        default=None,
        help="Stop after this many 1A chunks (debug; 200k rows each).",
    )
    parser.add_argument(
        "--chunksize",
        type=int,
        default=200_000,
        help="1A streaming chunk size (default matches spec §2.2).",
    )
    args = parser.parse_args(argv)

    if not (args.run_dir / "faiss.bin").exists():
        sys.exit(
            f"No FAISS index at {args.run_dir}/faiss.bin. "
            "Build one first via: py scripts/m3a_build_index.py"
        )

    settings = load_settings()
    min_size = settings.thresholds.clusters.min_size      # from config/thresholds.yaml
    print(f"Min cluster size (low-sample threshold): {min_size}")

    print(f"Loading M3a FAISS index from {args.run_dir} ...")
    t0 = time.perf_counter()
    product_index = ProductIndex.load(args.run_dir, settings.faiss)
    print(f"  loaded in {time.perf_counter() - t0:.2f}s — ntotal={product_index.size:,}")

    print("Rehydrating embeddings from FAISS index (make_direct_map + reconstruct_n) ...")
    t0 = time.perf_counter()
    embeddings = rehydrate_embeddings(product_index._index)   # noqa: SLF001
    rehydrate_secs = time.perf_counter() - t0
    print(
        f"  rehydrated {embeddings.shape[0]:,} × {embeddings.shape[1]}-d vectors "
        f"in {rehydrate_secs:.1f}s"
    )

    print("Building Product_ID → ProductType map from 1B ...")
    t0 = time.perf_counter()
    products = load_products(columns=["Product_ID", "ProductType_ID", "ProductType_Name"])
    pt_idx = build_pt_index_from_1b(products)
    print(
        f"  loaded {pt_idx.size:,} products covering "
        f"{len(set(pt_idx.pt_name_by_id.values())):,} distinct ProductTypes "
        f"in {time.perf_counter() - t0:.2f}s"
    )

    # Convert to plain dict[int, tuple[int, str]] expected by build_clusters.
    pt_index_dict = {
        pid: (pt_id, pt_idx.pt_name_by_id.get(pt_id, ""))
        for pid, pt_id in pt_idx.pt_id_by_product.items()
    }

    print(f"Loading M1 train split product IDs from {DEFAULT_SPLIT_DIR} ...")
    train_ids = _load_train_product_ids(DEFAULT_SPLIT_DIR)
    print(f"  {len(train_ids):,} train-split products")

    print(
        f"Streaming 1A in chunks of {args.chunksize:,} rows "
        f"(chunk_limit={args.chunk_limit}) ..."
    )

    def _chunks():
        for i, chunk in enumerate(
            iter_attribute_pairs(
                chunksize=args.chunksize,
                columns=["Product_ID", "Attribute_Name", "Attribute_Value"],
            )
        ):
            if args.chunk_limit is not None and i >= args.chunk_limit:
                break
            elapsed = time.perf_counter() - t_stream_start
            print(
                f"  chunk {i + 1:>3}: {len(chunk):,} rows  "
                f"elapsed={elapsed:.1f}s",
                flush=True,
            )
            yield chunk

    t_stream_start = time.perf_counter()
    store = build_clusters(
        embeddings=embeddings,
        product_ids=product_index.product_ids,
        pt_index=pt_index_dict,
        attribute_pairs_chunks=_chunks(),
        train_product_id_set=train_ids,
        min_cluster_size=min_size,
    )
    build_secs = time.perf_counter() - t_stream_start
    print(f"Cluster build complete in {build_secs:.1f}s")
    print(f"  total clusters: {len(store):,}")
    print(f"  low-sample clusters (N < {min_size}): {store.n_low_sample:,}")

    # PSD sanity check
    bad_psd = 0
    for s in store.stats:
        if s.low_sample or s.sigma_inv is None:
            continue
        eigvals = np.linalg.eigvalsh(s.sigma_inv)
        if (eigvals <= 0).any():
            bad_psd += 1
    n_full = len(store) - store.n_low_sample
    print(f"  Sigma_inv positive-definite check: {n_full - bad_psd}/{n_full} pass")
    if bad_psd:
        print(f"  WARNING: {bad_psd} clusters have non-PSD Sigma_inv (unexpected)")

    print(f"Persisting to {args.run_dir} ...")
    t0 = time.perf_counter()
    store.save(args.run_dir)
    print(f"  saved in {time.perf_counter() - t0:.2f}s")
    print(f"  centroids.parquet: {(args.run_dir / 'centroids.parquet').stat().st_size / 1024:.1f} KB")
    print(f"  cluster_cov.npz:   {(args.run_dir / 'cluster_cov.npz').stat().st_size / 1024 / 1024:.1f} MB")


if __name__ == "__main__":
    main()
