# ADR-005: Externalize the Confidence Threshold as Runtime Configuration

> Source of truth: [`0005-externalize-confidence-threshold-as-configuration.md`](https://github.com/AshrithaG/eparts/blob/main/docs/0005-externalize-confidence-threshold-as-configuration.md) in the eparts repo. This page is a copy for reading; edit the repo, not this page.

## Status

Tentative

## Context

The Routing Engine sends attributes with confidence above a threshold to auto-accept and attributes below the threshold to the Human Review Queue. The threshold is the most sensitive parameter in the system: it controls the tradeoff between accuracy (QA-1) and reviewer throughput. A threshold set too high pushes most attributes into review and overwhelms the catalog team, eliminating the labor savings the platform is meant to provide. A threshold set too low lets incorrect predictions through to PIMS, where they cause wrong parts to be ordered by contractors.

The threshold cannot be set during design because no model has yet been run against production-representative data. The team currently uses a placeholder of 0.85 with no empirical support. Refinement 1 in the project plan calibrates the threshold against ≥200 labeled submissions using precision-recall curves between 0.50 and 0.99. Per-attribute variance in accuracy may also drive a per-attribute threshold table rather than a single global value.

Hardcoding the threshold in the Routing Engine would require a code change and redeployment for every recalibration, which is incompatible with the iterative tuning the team expects across the pilot.

## Decision

The confidence threshold is externalized as runtime configuration read by the Routing Engine at startup. The configuration mechanism supports both a global threshold value and an optional per-attribute override table. Threshold changes take effect on application restart without any code change. The Routing Engine reads the threshold(s) once per pipeline run; threshold changes during a run do not affect already-routed attributes.

## Consequences

- The threshold can be retuned during pilot operation without engineering involvement beyond editing configuration and restarting the App Service.
- Per-attribute thresholds are supported architecturally without further code changes. If Refinement 1 reveals that some attributes (e.g., `SUPPLY_VOLTAGE`) are reliably predicted at 0.75 while others (e.g., `DESCRIPTION`) need 0.92, the per-attribute table can be populated.
- The threshold value is a configuration concern, not an architectural concern. This means that the architecture cannot guarantee an accuracy number; it can only guarantee that whatever threshold is set will be applied consistently. The actual accuracy guarantee depends on operational discipline around configuration management.
- Configuration drift is a risk. If the threshold is changed in production without recording the change in the audit trail, later analyses of model accuracy or reviewer workload may be impossible to interpret. The audit trail (ADR-009) records the threshold value alongside each routing decision to mitigate this.
- The decision is tentative because the threshold itself is unsupported. Once Refinement 1 produces evidence and a value is selected, this decision moves to Accepted.
- This decision interacts with monitorability (ADR-012): the threshold value is one of the baselines against which drift is measured. Changing the threshold resets the baseline.

## Requirements Traceability

- **FRs:** FR-4 (route based on threshold); FR-7 (configurable thresholds, calibration TBD); FR-9 (per-attribute routing using configurable thresholds)
- **QASs:** QAS-1 (accuracy lever); QAS-5 (threshold value is part of the drift baseline)
- **Scenarios:** SCEN-1 (above-threshold auto-accept), SCEN-2 (below-threshold review)
- **Validation:** VAL-2 (threshold drives routing behavior tested by VAL-2)
