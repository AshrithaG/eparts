"""M3a: encode all 1B product descriptions and build the FAISS index.

Implements V1_Engineering_Spec §4.3 [3a] + [3b] build step.

The output is an immutable run directory under ``artifacts/v1/`` containing:
    faiss.bin           FAISS-native serialization of the IVFFlat index
    ids.npy             aligned int64 Product_ID array
    encoder_hash.txt    encoder model_id (provenance)
    build_info.json     row count, dimension, hyperparameters, wall time

After a successful build, ``artifacts/v1/current/`` is updated to point
at this run (atomic rename so previous runs remain reachable).

Usage:
    py scripts/m3a_build_index.py                 # full build (~3-6 minutes CPU)
    py scripts/m3a_build_index.py --limit 5000    # quick smoke build
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import numpy as np

from src.config import load_settings
from src.data import load_products
from src.layer3_semantic import Encoder, build_index


ARTIFACTS_ROOT = REPO_ROOT / "artifacts" / "v1"


def _build_input_text(row: dict[str, object], columns: tuple[str, ...]) -> str:
    """Concatenate the configured description columns into one string."""
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
        "--limit",
        type=int,
        default=None,
        help="Encode only the first N products (debug / smoke).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Override the configured encoder batch size.",
    )
    parser.add_argument(
        "--no-current-alias",
        action="store_true",
        help="Skip updating artifacts/v1/current/ (useful for trial builds).",
    )
    args = parser.parse_args(argv)

    settings = load_settings()
    encoder = Encoder(settings.encoder)
    faiss_cfg = settings.faiss

    text_cols = tuple(faiss_cfg.input_text_columns)
    required_columns = ("Product_ID", *text_cols)
    print(f"Loading 1B columns: {list(required_columns)} ...")
    products = load_products(columns=required_columns)
    if args.limit is not None:
        products = products.head(args.limit).copy()
    n_rows = len(products)
    print(f"  loaded {n_rows:,} products")

    print("Assembling input text per product ...")
    texts: list[str] = []
    ids: list[int] = []
    skipped = 0
    for row in products.to_dict(orient="records"):
        text = _build_input_text(row, text_cols)
        if not text:
            skipped += 1
            continue
        texts.append(text)
        ids.append(int(row["Product_ID"]))
    print(f"  prepared {len(texts):,} non-empty rows (skipped {skipped:,} blanks)")

    print(f"Encoding via {settings.encoder.model_id} (batch={args.batch_size or settings.encoder.batch_size}) ...")
    t_enc = time.perf_counter()
    embeddings = encoder.encode(
        texts,
        batch_size=args.batch_size,
        show_progress=True,
    )
    enc_secs = time.perf_counter() - t_enc
    print(
        f"  encoded {embeddings.shape[0]:,} vectors of dim {embeddings.shape[1]} "
        f"in {enc_secs:.1f}s ({embeddings.shape[0] / max(enc_secs, 1e-6):.0f} rows/s)"
    )

    print(
        f"Building FAISS index: type={faiss_cfg.index_type}, nlist={faiss_cfg.nlist}, "
        f"nprobe={faiss_cfg.nprobe}, train={faiss_cfg.training_subset_size:,} ..."
    )
    t_idx = time.perf_counter()
    index = build_index(embeddings, np.asarray(ids, dtype=np.int64), faiss_cfg)
    idx_secs = time.perf_counter() - t_idx
    print(f"  index built in {idx_secs:.1f}s — ntotal={index.size:,}")

    # Run directory
    run_id = datetime.now(timezone.utc).strftime("run_%Y%m%d_%H%M%S")
    run_dir = ARTIFACTS_ROOT / run_id
    print(f"Persisting to {run_dir} ...")
    index.save(run_dir)
    (run_dir / "encoder_hash.txt").write_text(settings.encoder.model_id + "\n", encoding="utf-8")
    info = {
        "run_id": run_id,
        "encoder_model_id": settings.encoder.model_id,
        "encoder_dim": int(embeddings.shape[1]),
        "n_indexed": int(index.size),
        "n_skipped_blank": skipped,
        "limit": args.limit,
        "faiss_index_type": faiss_cfg.index_type,
        "faiss_nlist": faiss_cfg.nlist,
        "faiss_nprobe": faiss_cfg.nprobe,
        "faiss_top_k": faiss_cfg.top_k,
        "encode_seconds": round(enc_secs, 1),
        "index_build_seconds": round(idx_secs, 1),
    }
    (run_dir / "build_info.json").write_text(json.dumps(info, indent=2), encoding="utf-8")

    if not args.no_current_alias:
        current = ARTIFACTS_ROOT / "current"
        # Symlinks are awkward on Windows — copy a tiny pointer file instead.
        current.mkdir(exist_ok=True)
        (current / "RUN_ID").write_text(run_id + "\n", encoding="utf-8")
        # Also mirror the small files so consumers can read them through `current/`.
        for fname in ("faiss.bin", "ids.npy", "encoder_hash.txt", "build_info.json"):
            shutil.copy2(run_dir / fname, current / fname)
        print(f"  updated {current} → {run_id}")

    print()
    print("Build summary:")
    for k, v in info.items():
        print(f"  {k:>22}: {v}")


if __name__ == "__main__":
    main()
