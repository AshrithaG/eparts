"""Split reproducibility & invariants (M1 acceptance tests)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.data.split import (
    MIN_PRODUCTS_FOR_FULL_SPLIT,
    stratified_product_split,
    write_splits,
    load_splits,
)


def _make_products(
    n_pts: int = 20,
    per_pt: int = 30,
    singleton_pts: int = 3,
) -> pd.DataFrame:
    """Synthetic 1B-shaped frame: most PTs have `per_pt` products; a few have 1."""
    rows = []
    product_id = 1
    for pt in range(n_pts):
        for _ in range(per_pt):
            rows.append({"Product_ID": product_id, "ProductType_ID": pt, "Category_ID": pt // 5})
            product_id += 1
    for pt in range(n_pts, n_pts + singleton_pts):
        rows.append({"Product_ID": product_id, "ProductType_ID": pt, "Category_ID": 99})
        product_id += 1
    return pd.DataFrame(rows)


def test_split_reproducible_with_same_seed():
    products = _make_products()
    a = stratified_product_split(products, seed=42)
    b = stratified_product_split(products, seed=42)
    for name in ("train", "val", "test"):
        pd.testing.assert_frame_equal(a[name], b[name])


def test_split_changes_with_different_seed():
    products = _make_products()
    a = stratified_product_split(products, seed=42)
    b = stratified_product_split(products, seed=123)
    assert not a["test"]["Product_ID"].equals(b["test"]["Product_ID"])


def test_no_product_duplicated_across_splits():
    products = _make_products()
    splits = stratified_product_split(products, seed=42)
    all_ids = pd.concat([splits[k]["Product_ID"] for k in ("train", "val", "test")])
    assert all_ids.is_unique, "product IDs must not repeat across splits"


def test_row_count_invariant():
    products = _make_products()
    splits = stratified_product_split(products, seed=42)
    total = sum(len(splits[k]) for k in ("train", "val", "test"))
    assert total == len(products), "every product must land in exactly one split"


def test_every_sufficient_pt_appears_in_all_splits():
    products = _make_products(n_pts=20, per_pt=30, singleton_pts=3)
    splits = stratified_product_split(products, seed=42)
    counts = products.groupby("ProductType_ID").size()
    full_split_pts = set(counts[counts >= MIN_PRODUCTS_FOR_FULL_SPLIT].index)
    for name in ("train", "val", "test"):
        present = set(splits[name]["ProductType_ID"].unique())
        missing = full_split_pts - present
        assert not missing, f"{name} is missing ProductTypes: {missing}"


def test_singleton_productypes_land_in_train_only():
    products = _make_products(n_pts=5, per_pt=10, singleton_pts=4)
    splits = stratified_product_split(products, seed=42)
    counts = products.groupby("ProductType_ID").size()
    singleton_pts = set(counts[counts < MIN_PRODUCTS_FOR_FULL_SPLIT].index)
    train_pts = set(splits["train"]["ProductType_ID"].unique())
    val_pts = set(splits["val"]["ProductType_ID"].unique())
    test_pts = set(splits["test"]["ProductType_ID"].unique())
    assert singleton_pts <= train_pts
    assert not (singleton_pts & val_pts)
    assert not (singleton_pts & test_pts)


def test_ratios_approximately_respected():
    products = _make_products(n_pts=20, per_pt=100, singleton_pts=0)
    splits = stratified_product_split(products, seed=42)
    total = len(products)
    train_frac = len(splits["train"]) / total
    val_frac = len(splits["val"]) / total
    test_frac = len(splits["test"]) / total
    # Per-PT rounding means we won't hit 0.80/0.10/0.10 exactly, but close.
    assert 0.75 <= train_frac <= 0.85
    assert 0.05 <= val_frac <= 0.15
    assert 0.05 <= test_frac <= 0.15


def test_ratios_must_sum_to_one():
    products = _make_products()
    with pytest.raises(ValueError):
        stratified_product_split(products, ratios=(0.7, 0.2, 0.2), seed=42)


def test_dropped_null_productype_rows():
    products = _make_products(n_pts=3, per_pt=10, singleton_pts=0)
    # Inject 2 null-PT rows that must be silently dropped.
    nulls = pd.DataFrame(
        [
            {"Product_ID": 9001, "ProductType_ID": np.nan, "Category_ID": 0},
            {"Product_ID": 9002, "ProductType_ID": np.nan, "Category_ID": 0},
        ]
    )
    products = pd.concat([products, nulls], ignore_index=True)
    splits = stratified_product_split(products, seed=42)
    total = sum(len(splits[k]) for k in ("train", "val", "test"))
    assert total == len(products) - 2
    all_ids = pd.concat([splits[k]["Product_ID"] for k in ("train", "val", "test")])
    assert 9001 not in set(all_ids)
    assert 9002 not in set(all_ids)


def test_write_then_load_roundtrip(tmp_path: Path):
    products = _make_products()
    splits = stratified_product_split(products, seed=42)
    paths = write_splits(splits, out_dir=tmp_path)
    assert paths.train.exists() and paths.val.exists() and paths.test.exists()
    reloaded = load_splits(split_dir=tmp_path)
    for name in ("train", "val", "test"):
        pd.testing.assert_frame_equal(
            splits[name].reset_index(drop=True),
            reloaded[name].reset_index(drop=True),
            check_dtype=False,
        )
