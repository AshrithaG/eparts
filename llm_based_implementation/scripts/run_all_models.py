"""Run the ProductType-classification benchmark across several local models
on the IDENTICAL sample, and emit a comparison table.

All models see the same products (fixed seed), same shortlist size, same
temperature=0 — so the only variable is the model. Reuses
`classify_product_types.run_benchmark`.

Usage:
    python scripts/run_all_models.py
    python scripts/run_all_models.py --n 100 --shortlist 12
    python scripts/run_all_models.py --models qwen2.5:7b-instruct phi4

By default it benchmarks whatever models are installed in Ollama out of the
target set; it skips (with a note) any that are not present, rather than
pulling — pull with scripts/pull_models.ps1 first.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import classify_product_types as C  # noqa: E402

# The target set, in rough ascending size order. Entries are (display_label,
# [candidate ollama tags]); the first installed candidate is used.
TARGET_MODELS = [
    ("llama3.2:3b",  ["llama3.2:3b-instruct", "llama3.2:3b"]),
    ("qwen2.5:7b",   ["qwen2.5:7b-instruct", "qwen2.5:7b"]),
    ("llama3.1:8b",  ["llama3.1:8b-instruct", "llama3.1:8b"]),
    ("phi4:14b",     ["phi4", "phi4:14b"]),
    ("qwen2.5:14b",  ["qwen2.5:14b-instruct", "qwen2.5:14b"]),
]

# Approx. parameter counts for the cost/accuracy view.
PARAMS_B = {
    "llama3.2:3b": 3, "qwen2.5:7b": 7, "llama3.1:8b": 8, "phi4:14b": 14, "qwen2.5:14b": 14,
}


def installed_models(host: str) -> set[str]:
    import ollama
    c = ollama.Client(host=host)
    out = set()
    for m in c.list().get("models", []):
        name = m.get("model") or m.get("name")
        if name:
            out.add(name)
    return out


def resolve(candidates: list[str], present: set[str]) -> str | None:
    for tag in candidates:
        if tag in present:
            return tag
        # ollama sometimes reports the tag with an implicit ":latest"
        if f"{tag}:latest" in present:
            return f"{tag}:latest"
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="http://localhost:11434")
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--shortlist", type=int, default=12)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--models", nargs="*", default=None,
                    help="Override: explicit ollama tags to benchmark.")
    args = ap.parse_args()

    try:
        present = installed_models(args.host)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR contacting Ollama at {args.host}: {e}", file=sys.stderr)
        return 2
    print(f"Installed models: {sorted(present)}\n")

    products, sample, corpus_tokens = C.build_sample(args.seed, args.n, args.all)
    print(f"Sample: {len(sample)} products | {len({p['pt_id'] for p in products})} "
          f"ProductTypes in catalog | shortlist={args.shortlist} | temp={args.temperature}\n")

    # Decide which models to run.
    if args.models:
        plan = [(m, m) for m in args.models]
    else:
        plan = []
        for label, candidates in TARGET_MODELS:
            tag = resolve(candidates, present)
            if tag:
                plan.append((label, tag))
            else:
                print(f"SKIP {label}: none of {candidates} installed.")
        print()

    summaries: list[dict] = []
    for label, tag in plan:
        print("#" * 72)
        print(f"# {label}  (ollama tag: {tag})")
        print("#" * 72)
        t0 = time.time()
        s = C.run_benchmark(
            model=tag, sample=sample, products=products, corpus_tokens=corpus_tokens,
            host=args.host, shortlist=args.shortlist, seed=args.seed,
            temperature=args.temperature, verbose=False,
        )
        s["label"] = label
        s["params_b"] = PARAMS_B.get(label)
        summaries.append(s)
        print(f"  -> overall_accuracy={s['overall_accuracy']:.3f}  "
              f"acc_in_shortlist={s['accuracy_when_true_in_shortlist']:.3f}  "
              f"high_conf_acc={s['high_conf_accuracy']}  "
              f"sec/item={s['sec_per_item']}  ({time.time()-t0:.0f}s total)\n")

    # Persist combined summary.
    out_dir = ROOT / "artifacts"
    out_dir.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    combined = out_dir / f"model_comparison_{stamp}.json"
    combined.write_text(json.dumps({
        "n": len(sample), "shortlist": args.shortlist, "seed": args.seed,
        "temperature": args.temperature, "summaries": summaries,
    }, indent=2), encoding="utf-8")

    # Print the comparison table.
    print("\n" + "=" * 96)
    print("MODEL COMPARISON  (same {} products, shortlist={}, temp={}, seed={})".format(
        len(sample), args.shortlist, args.temperature, args.seed))
    print("=" * 96)
    hdr = f"{'Model':14}{'Params':>7}{'Overall':>9}{'In-list':>9}{'HiConf':>8}{'Wrong@1.0':>11}{'sec/item':>10}"
    print(hdr)
    print("-" * 96)
    for s in summaries:
        hc = s["high_conf_accuracy"]
        hc_s = f"{hc:.2f}" if hc is not None else "n/a"
        wrong1 = f"{s['wrong_asserted_at_conf_1']}/{s['n_wrong']}"
        print(f"{s['label']:14}{str(s['params_b'])+'B':>7}"
              f"{s['overall_accuracy']*100:>8.1f}%"
              f"{s['accuracy_when_true_in_shortlist']*100:>8.1f}%"
              f"{hc_s:>8}{wrong1:>11}{s['sec_per_item']:>10}")
    print("-" * 96)
    print(f"Retrieval shortlist recall (same for all): {summaries[0]['shortlist_recall']*100:.1f}%"
          if summaries else "no models run")
    print("Stat-track M3b reference: 94.69% overall ProductType accuracy.")
    print(f"\nCombined summary: {combined}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
