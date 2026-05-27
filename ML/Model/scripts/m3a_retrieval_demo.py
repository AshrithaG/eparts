"""M3a: retrieval smoke test — query the FAISS index and inspect neighbors.

Loads ``artifacts/v1/current/`` and runs a handful of fixed queries
end-to-end (encode → search → resolve Product_ID back to 1B metadata).
Useful for confirming the encoder + index agree on a sensible
neighborhood.

Usage:
    py scripts/m3a_retrieval_demo.py
    py scripts/m3a_retrieval_demo.py --top-k 10 --query "thermistor probe"
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.config import load_settings
from src.data import load_products
from src.layer3_semantic import Encoder, ProductIndex


DEFAULT_QUERIES = [
    "temperature sensor 24 VAC strap-on thermistor",
    "damper actuator 0-10 VDC control",
    "differential pressure transmitter for HVAC",
    "Johnson Controls T-6000",
]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", action="append", help="Run a custom query (repeatable).")
    parser.add_argument("--top-k", type=int, default=10, help="Neighbors to print per query.")
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=REPO_ROOT / "artifacts" / "v1" / "current",
        help="Run directory containing faiss.bin + ids.npy.",
    )
    args = parser.parse_args(argv)

    if not (args.run_dir / "faiss.bin").exists():
        sys.exit(
            f"No FAISS index at {args.run_dir}/faiss.bin. "
            "Build one first via: py scripts/m3a_build_index.py"
        )

    settings = load_settings()

    print(f"Loading index from {args.run_dir} ...")
    t0 = time.perf_counter()
    index = ProductIndex.load(args.run_dir, settings.faiss)
    print(f"  loaded in {time.perf_counter() - t0:.2f}s — ntotal={index.size:,}, dim={index.dimension}")

    print("Loading encoder ...")
    encoder = Encoder(settings.encoder)
    _ = encoder.encode_one("warm up")     # forces model load before timing

    print("Loading 1B metadata for result resolution ...")
    catalog = (
        load_products(
            columns=[
                "Product_ID",
                "Product_Number",
                "Manufacturer_Name",
                "ProductType_Name",
                "Short_Description",
            ]
        )
        .set_index("Product_ID", drop=False)
    )

    queries = args.query if args.query else DEFAULT_QUERIES

    for query in queries:
        print()
        print(f"QUERY: {query!r}")
        t0 = time.perf_counter()
        vector = encoder.encode_one(query)
        enc_ms = (time.perf_counter() - t0) * 1000
        t0 = time.perf_counter()
        [hits] = index.search(vector, k=args.top_k)
        search_ms = (time.perf_counter() - t0) * 1000
        print(f"  encode={enc_ms:.1f} ms  search={search_ms:.2f} ms  total={enc_ms + search_ms:.1f} ms")
        for rank, hit in enumerate(hits, start=1):
            try:
                row = catalog.loc[hit.product_id]
            except KeyError:
                print(f"    {rank:2d}. id={hit.product_id} (not in catalog?)")
                continue
            short = (row["Short_Description"] or "")[:70]
            print(
                f"    {rank:2d}. score={hit.score:.4f}  "
                f"id={hit.product_id:>8}  "
                f"mfg={row['Manufacturer_Name']!s:<22.22}  "
                f"pt={row['ProductType_Name']!s:<22.22}  "
                f"{short!s}"
            )


if __name__ == "__main__":
    main()
