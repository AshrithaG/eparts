"""M1: build train/val/test splits from 1B and persist to data/splits/.

Usage:  py scripts/m1_build_splits.py
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.data import (
    load_products,
    stratified_product_split,
    write_splits,
)
from src.data.split import DEFAULT_SPLIT_DIR, DEFAULT_SEED


def main() -> None:
    print("Loading 1B_Product_Master.csv ...")
    products = load_products(columns=["Product_ID", "ProductType_ID", "Category_ID"])
    print(f"  loaded {len(products):,} products, {products['ProductType_ID'].nunique()} ProductTypes")

    print(f"Building splits (seed={DEFAULT_SEED}, ratios=80/10/10, stratified by ProductType_ID) ...")
    splits = stratified_product_split(products, seed=DEFAULT_SEED)

    total = sum(len(v) for v in splits.values())
    for name, df in splits.items():
        frac = len(df) / total if total else 0
        pts = df["ProductType_ID"].nunique()
        print(f"  {name:5s}: {len(df):>8,}  ({frac:.2%})  across {pts:>4} ProductTypes")

    out = DEFAULT_SPLIT_DIR
    print(f"Writing parquet to {out} ...")
    paths = write_splits(splits, out_dir=out)
    for name, path in paths.as_dict().items():
        size_kb = path.stat().st_size / 1024
        print(f"  {name:5s}: {path}  ({size_kb:,.1f} KB)")


if __name__ == "__main__":
    main()
