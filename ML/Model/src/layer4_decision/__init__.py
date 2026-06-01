"""Layer 4 — fusion, caps, routing, σ calibration, and online updates.

Implements V1_Engineering_Spec §4.4 (fusion + routing + feedback loop)
and §5.3 (σ calibration grid search). See also
:mod:`src.layer3_semantic.scoring` for the σ injection surface that
fusion's calibrated values feed back into.
"""

from .calibration import (
    SigmaCalibrator,
    SigmaEntry,
    SigmaTable,
    ValQuery,
    brier_score,
    expected_calibration_error,
)
from .feedback import (
    ClusterNotFoundError,
    FeedbackEvent,
    FeedbackStore,
    apply_confirm,
    apply_pushback,
)
from .fusion import Layer4Decision

__all__ = [
    "ClusterNotFoundError",
    "FeedbackEvent",
    "FeedbackStore",
    "Layer4Decision",
    "SigmaCalibrator",
    "SigmaEntry",
    "SigmaTable",
    "ValQuery",
    "apply_confirm",
    "apply_pushback",
    "brier_score",
    "expected_calibration_error",
]
