"""Product-level stratified splits by ProductType.

We split at the product level (not the 1A-row level) to prevent leakage:
if a single product's attribute rows were spread across train/val/test,
the encoder would see the same description at both train and eval time.

ProductTypes with fewer than 3 products are placed entirely in train —
they cannot supply both a val and a test sample, and the cluster-level
evaluation will simply not see them. This is acceptable: the spec's
Layer 3 already requires >= 5 cluster members to produce a score.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd

from .loader import load_products

DEFAULT_SPLIT_DIR = Path(__file__).resolve().parents[2] / "data" / "splits"
DEFAULT_RATIOS = (0.80, 0.10, 0.10)
DEFAULT_SEED = 42
MIN_PRODUCTS_FOR_FULL_SPLIT = 3


@dataclass(frozen=True)
class SplitPaths:
    train: Path
    val: Path
    test: Path

    def as_dict(self) -> dict[str, Path]:
        return {"train": self.train, "val": self.val, "test": self.test}


def _split_one_productype(
    product_ids: np.ndarray,
    rng: np.random.Generator,
    ratios: tuple[float, float, float],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    n = len(product_ids)
    if n < MIN_PRODUCTS_FOR_FULL_SPLIT:
        return product_ids, np.empty(0, dtype=product_ids.dtype), np.empty(0, dtype=product_ids.dtype)

    permuted = product_ids[rng.permutation(n)]
    _, val_ratio, test_ratio = ratios
    n_val = max(1, int(round(n * val_ratio)))
    n_test = max(1, int(round(n * test_ratio)))
    # Guarantee train gets at least 1.
    while n - n_val - n_test < 1:
        if n_val > 1:
            n_val -= 1
        else:
            n_test -= 1
    n_train = n - n_val - n_test
    train = permuted[:n_train]
    val = permuted[n_train : n_train + n_val]
    test = permuted[n_train + n_val :]
    return train, val, test


def stratified_product_split(
    products: pd.DataFrame | None = None,
    ratios: tuple[float, float, float] = DEFAULT_RATIOS,
    seed: int = DEFAULT_SEED,
) -> dict[str, pd.DataFrame]:
    """Split products into train/val/test, stratified by ProductType_ID.

    Returns a dict with three DataFrames, each containing Product_ID,
    ProductType_ID, and Category_ID columns. Deterministic for a fixed seed.
    """
    if abs(sum(ratios) - 1.0) > 1e-9:
        raise ValueError(f"ratios must sum to 1.0, got {ratios}")

    if products is None:
        products = load_products(columns=["Product_ID", "ProductType_ID", "Category_ID"])

    required = {"Product_ID", "ProductType_ID"}
    missing = required - set(products.columns)
    if missing:
        raise ValueError(f"products is missing required columns: {missing}")

    # Drop rows with null ProductType_ID (cannot be stratified).
    usable = products.dropna(subset=["ProductType_ID"]).copy()
    # Stable ordering before permutation — seed then controls everything.
    usable = usable.sort_values("Product_ID").reset_index(drop=True)

    rng = np.random.default_rng(seed)
    train_parts: list[pd.DataFrame] = []
    val_parts: list[pd.DataFrame] = []
    test_parts: list[pd.DataFrame] = []

    for pt_id, group in usable.groupby("ProductType_ID", sort=True):
        ids = group["Product_ID"].to_numpy()
        train_ids, val_ids, test_ids = _split_one_productype(ids, rng, ratios)
        if len(train_ids):
            train_parts.append(group[group["Product_ID"].isin(train_ids)])
        if len(val_ids):
            val_parts.append(group[group["Product_ID"].isin(val_ids)])
        if len(test_ids):
            test_parts.append(group[group["Product_ID"].isin(test_ids)])

    def _concat(parts: list[pd.DataFrame]) -> pd.DataFrame:
        if not parts:
            return usable.iloc[0:0].copy()
        return (
            pd.concat(parts, ignore_index=True)
            .sort_values("Product_ID")
            .reset_index(drop=True)
        )

    return {
        "train": _concat(train_parts),
        "val": _concat(val_parts),
        "test": _concat(test_parts),
    }


def write_splits(
    splits: Mapping[str, pd.DataFrame],
    out_dir: Path = DEFAULT_SPLIT_DIR,
) -> SplitPaths:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = SplitPaths(
        train=out_dir / "train.parquet",
        val=out_dir / "val.parquet",
        test=out_dir / "test.parquet",
    )
    for name, path in paths.as_dict().items():
        splits[name].to_parquet(path, index=False)
    return paths


def load_splits(split_dir: Path = DEFAULT_SPLIT_DIR) -> dict[str, pd.DataFrame]:
    return {name: pd.read_parquet(path) for name, path in SplitPaths(
        train=split_dir / "train.parquet",
        val=split_dir / "val.parquet",
        test=split_dir / "test.parquet",
    ).as_dict().items()}
