"""Raw-data loaders for the_standard_data/.

1A is 1.4 GB — never load fully; use iter_attribute_pairs with chunks.
1B (~100 MB) and 2A (~0.4 MB) fit in memory and are loaded directly.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterator, Iterable

import pandas as pd

RAW_DIR = Path(__file__).resolve().parents[2] / "the_standard_data"

PRODUCTS_FILE = RAW_DIR / "1B_Product_Master.csv"
ATTRIBUTE_PAIRS_FILE = RAW_DIR / "1A_Product_Attribute_Pairs.csv"
VALUES_FILE = RAW_DIR / "2A_Values_Per_Attribute.csv"
DOC_LINKS_FILE = RAW_DIR / "1A_Product_Document_Links.csv"

DEFAULT_CHUNKSIZE = 200_000

PRODUCTS_DTYPES = {
    "Product_ID": "int64",
    "Product_Number": "string",
    "Product_Number_Custom": "string",
    "Product_Name": "string",
    "Short_Description": "string",
    "Full_Description": "string",
    "Extended_Description_Pre": "string",
    "Extended_Description_Post": "string",
    "Manufacturer_ID": "Int64",
    "Manufacturer_Name": "string",
    "ProductType_ID": "Int64",
    "ProductType_Name": "string",
    "Category_ID": "Int64",
}

PAIRS_DTYPES = {
    "Product_ID": "int64",
    "Product_Number": "string",
    "Manufacturer_Name": "string",
    "ProductType_Name": "string",
    "Short_Description": "string",
    "Full_Description": "string",
    "Extended_Description": "string",
    "Attribute_Name": "string",
    "Attribute_Value": "string",
    "DisplayText": "string",
    "Unit_Suffix": "string",
    "DigitalValue": "float64",
    "RangeLow": "float64",
    "RangeHigh": "float64",
}

VALUES_DTYPES = {
    "Attribute_Name": "string",
    "Attribute_ID": "Int64",
    "Value": "string",
    "DisplayText": "string",
    "Unit_Suffix": "string",
    "Usage_Count": "Int64",
}


def load_products(columns: Iterable[str] | None = None) -> pd.DataFrame:
    """Load 1B_Product_Master.csv fully into memory."""
    usecols = list(columns) if columns is not None else None
    return pd.read_csv(
        PRODUCTS_FILE,
        usecols=usecols,
        dtype={c: t for c, t in PRODUCTS_DTYPES.items() if usecols is None or c in usecols},
        low_memory=False,
    )


def load_values_per_attribute() -> pd.DataFrame:
    """Load 2A_Values_Per_Attribute.csv fully into memory."""
    return pd.read_csv(VALUES_FILE, dtype=VALUES_DTYPES)


def iter_attribute_pairs(
    chunksize: int = DEFAULT_CHUNKSIZE,
    columns: Iterable[str] | None = None,
) -> Iterator[pd.DataFrame]:
    """Stream 1A_Product_Attribute_Pairs.csv in chunks.

    Memory stays bounded — each chunk is ~chunksize rows × ~14 columns.
    Caller is responsible for aggregation / filtering.
    """
    usecols = list(columns) if columns is not None else None
    dtype = {c: t for c, t in PAIRS_DTYPES.items() if usecols is None or c in usecols}
    return pd.read_csv(
        ATTRIBUTE_PAIRS_FILE,
        chunksize=chunksize,
        usecols=usecols,
        dtype=dtype,
        low_memory=False,
    )


def count_attribute_pair_rows(chunksize: int = DEFAULT_CHUNKSIZE) -> int:
    """Stream-count rows in 1A without loading it into memory."""
    total = 0
    for chunk in iter_attribute_pairs(chunksize=chunksize, columns=["Product_ID"]):
        total += len(chunk)
    return total
