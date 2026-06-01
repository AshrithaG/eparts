"""M7: launch the REST inference service with uvicorn.

Implements V1_Engineering_Spec §7.2 M7. Loads real artifacts from a run
directory (default artifacts/v1/current), wires the FastAPI app via
:func:`src.service.bootstrap.build_default_app`, and serves it.

Usage:
    py scripts/m7_serve.py                          # serve current/ on :8000
    py scripts/m7_serve.py --port 9000 --no-feedback
    py scripts/m7_serve.py --run-dir artifacts/v1/run_<ts>

Endpoints once running:
    POST /predict    GET /healthz    GET /metrics    POST /feedback

Note: startup loads the 293 MB FAISS index + 2.7 GB covariance artifact +
the encoder — expect ~25-30 s before the service is ready.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path,
                        default=REPO_ROOT / "artifacts" / "v1" / "current")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-feedback", action="store_true",
                        help="Disable /feedback (read-only deployment).")
    parser.add_argument("--baseline-csv", type=Path, default=None,
                        help="M5 confidence_dist.csv for the drift signal.")
    args = parser.parse_args(argv)

    if not (args.run_dir / "faiss.bin").exists():
        sys.exit(f"no faiss.bin at {args.run_dir} — build artifacts first (see README).")

    import uvicorn

    from src.service.bootstrap import build_default_app

    print(f"Loading artifacts from {args.run_dir} (this takes ~25-30 s) ...")
    app = build_default_app(
        run_dir=args.run_dir,
        baseline_csv=args.baseline_csv,
        enable_feedback=not args.no_feedback,
    )
    print(f"Ready. Serving on http://{args.host}:{args.port}  "
          f"(feedback {'disabled' if args.no_feedback else 'enabled'})")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
