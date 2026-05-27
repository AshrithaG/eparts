"""Layer 4 — fusion, caps, routing, and σ calibration.

Implements V1_Engineering_Spec §4.4 (fusion + routing) and §5.3
(σ calibration grid search). See also :mod:`src.layer3_semantic.scoring`
for the σ injection surface that fusion's calibrated values feed back into.
"""

from .calibration import (
    SigmaCalibrator,
    SigmaEntry,
    SigmaTable,
    ValQuery,
    brier_score,
    expected_calibration_error,
)
from .fusion import Layer4Decision

__all__ = [
    "Layer4Decision",
    "SigmaCalibrator",
    "SigmaEntry",
    "SigmaTable",
    "ValQuery",
    "brier_score",
    "expected_calibration_error",
]
