"""M7 — REST inference service + Prometheus telemetry.

Implements V1_Engineering_Spec §7.2 M7 + §8 (CAP-ML-01/04).

    src.service.app        create_app(...) — FastAPI factory (DI for tests)
    src.service.bootstrap  build_default_app(...) — loads real artifacts
    src.service.metrics    ServiceMetrics — Prometheus collectors + drift KL
    src.service.schemas    pydantic request/response models
"""

from .app import create_app
from .metrics import ServiceMetrics, load_baseline_conf_hist

__all__ = ["create_app", "ServiceMetrics", "load_baseline_conf_hist"]
