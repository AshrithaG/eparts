"""M6: reviewer-feedback CLI for online cluster updates.

Implements V1_Engineering_Spec §4.4 feedback loop. Wraps
:class:`src.layer4_decision.FeedbackStore` with four subcommands:

    confirm   — reviewer confirms value V for (PT, attribute) given a query
    correct   — reviewer corrects a confidently-wrong prediction
    replay    — reapply the audit log onto the current centroids snapshot
    snapshot  — persist the in-memory store to centroids.parquet

The query embedding for confirm/correct comes from EITHER:
    --text "<description>"        encode this string with the configured encoder
    --product-id <int>           look up the product's description in 1B and encode it

Usage examples:
    py scripts/m6_feedback_cli.py confirm  --pt 388 --attr "FLOW RATE" --value "002.00 - 002.99" --product-id 354844 --reviewer alice
    py scripts/m6_feedback_cli.py correct  --pt 388 --attr "INPUT POWER" --wrong "24 VAC/VDC" --true "24 VDC" --text "3in 2-way PIV chilled water" --reviewer bob
    py scripts/m6_feedback_cli.py replay
    py scripts/m6_feedback_cli.py snapshot

Notes:
    * confirm / correct mutate the in-memory store and append to the audit
      log immediately. They do NOT rewrite centroids.parquet — run
      ``snapshot`` to persist, or rely on ``replay`` at the next startup.
    * λ (error pushback) is read from config/thresholds.yaml; never passed
      on the CLI (it is FROZEN per spec §6.1).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")                       # type: ignore[attr-defined]

import numpy as np

from src.config import load_settings
from src.layer3_semantic import ClusterStore, Encoder
from src.layer4_decision import ClusterNotFoundError, FeedbackStore


def _resolve_query_vector(args, settings) -> np.ndarray:
    """Encode --text, or look up --product-id in 1B and encode its description."""
    if args.text:
        encoder = Encoder(settings.encoder)
        return encoder.encode_one(args.text)
    if args.product_id is not None:
        from src.data import load_products
        cols = ["Product_ID", *settings.faiss.input_text_columns]
        products = load_products(columns=cols).set_index("Product_ID", drop=False)
        if args.product_id not in products.index:
            sys.exit(f"product_id {args.product_id} not found in 1B")
        row = products.loc[args.product_id]
        parts = []
        for c in settings.faiss.input_text_columns:
            v = row.get(c)
            if v is not None and str(v).strip() and str(v).lower() != "nan":
                parts.append(str(v).strip())
        text = " ".join(parts)
        if not text:
            sys.exit(f"product_id {args.product_id} has empty description")
        encoder = Encoder(settings.encoder)
        return encoder.encode_one(text)
    sys.exit("confirm/correct require either --text or --product-id")


def _make_store(args, settings) -> FeedbackStore:
    run_dir = args.run_dir
    if not (run_dir / "centroids.parquet").exists():
        sys.exit(f"no centroids.parquet at {run_dir} — run scripts/m3b_build_clusters.py first")
    cluster_store = ClusterStore.load(run_dir)
    return FeedbackStore(
        cluster_store,
        artifact_dir=run_dir,
        pushback_lambda=settings.thresholds.online_updates.pushback_lambda,
    )


def _cmd_confirm(args, settings) -> None:
    fb = _make_store(args, settings)
    q = _resolve_query_vector(args, settings)
    try:
        updated = fb.confirm(args.pt, args.attr, args.value, q, reviewer_id=args.reviewer)
    except ClusterNotFoundError as e:
        sys.exit(str(e))
    print(f"CONFIRM applied: (pt={args.pt}, attr={args.attr!r}, value={args.value!r})")
    print(f"  n: {updated.n - 1} -> {updated.n}")
    print(f"  audit appended: {fb.audit_path}")
    print("  (run `snapshot` to persist centroids.parquet)")


def _cmd_correct(args, settings) -> None:
    fb = _make_store(args, settings)
    q = _resolve_query_vector(args, settings)
    try:
        wrong, true = fb.correct(
            args.pt, args.attr, value_wrong=args.wrong, value_true=args.true,
            q=q, reviewer_id=args.reviewer,
        )
    except ClusterNotFoundError as e:
        sys.exit(str(e))
    print(f"CORRECT applied: (pt={args.pt}, attr={args.attr!r})")
    print(f"  pushback on  {args.wrong!r}: n unchanged ({wrong.n}); μ nudged away from query")
    print(f"  confirm on   {args.true!r}: n -> {true.n}")
    print(f"  audit appended: {fb.audit_path}")
    print("  (run `snapshot` to persist centroids.parquet)")


def _cmd_replay(args, settings) -> None:
    fb = _make_store(args, settings)
    n = fb.replay()
    print(f"replayed {n} audit event(s) onto {args.run_dir / 'centroids.parquet'}")
    if n:
        print("  (run `snapshot` to persist the replayed state)")


def _cmd_snapshot(args, settings) -> None:
    fb = _make_store(args, settings)
    # If asked, replay the audit log first so the snapshot is fully current.
    if args.with_replay:
        n = fb.replay()
        print(f"  replayed {n} audit event(s) before snapshot")
    path = fb.snapshot()
    print(f"snapshot written: {path} ({path.stat().st_size / 1024:.1f} KB)")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-dir", type=Path,
        default=REPO_ROOT / "artifacts" / "v1" / "current",
        help="Run dir containing centroids.parquet + the audit log.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_confirm = sub.add_parser("confirm", help="Reviewer confirms a value.")
    p_confirm.add_argument("--pt", type=int, required=True)
    p_confirm.add_argument("--attr", required=True)
    p_confirm.add_argument("--value", required=True)
    p_confirm.add_argument("--text", default=None)
    p_confirm.add_argument("--product-id", type=int, default=None)
    p_confirm.add_argument("--reviewer", required=True)

    p_correct = sub.add_parser("correct", help="Reviewer corrects a wrong prediction.")
    p_correct.add_argument("--pt", type=int, required=True)
    p_correct.add_argument("--attr", required=True)
    p_correct.add_argument("--wrong", required=True, help="The confidently-wrong value (pushback target).")
    p_correct.add_argument("--true", required=True, help="The correct value (confirm target).")
    p_correct.add_argument("--text", default=None)
    p_correct.add_argument("--product-id", type=int, default=None)
    p_correct.add_argument("--reviewer", required=True)

    sub.add_parser("replay", help="Reapply the audit log onto the current snapshot.")

    p_snap = sub.add_parser("snapshot", help="Persist the in-memory store to centroids.parquet.")
    p_snap.add_argument("--with-replay", action="store_true",
                        help="Replay the audit log before snapshotting.")

    args = parser.parse_args(argv)
    settings = load_settings()

    if args.command == "confirm":
        _cmd_confirm(args, settings)
    elif args.command == "correct":
        _cmd_correct(args, settings)
    elif args.command == "replay":
        _cmd_replay(args, settings)
    elif args.command == "snapshot":
        _cmd_snapshot(args, settings)


if __name__ == "__main__":
    main()
