"""Typed configuration loader for the V1 pipeline.

All tunable parameters live in YAML under ``config/`` (spec §11.3). This
module reads those files into immutable dataclasses so that:

  * Hard-coded values never appear in ``src/`` (enforced by code review,
    not by lint).
  * Layer code accepts a typed config object via its constructor, which
    keeps tests painless (pass a hand-built ``Settings`` instance).
  * Frozen-vs-tunable distinctions stay close to the values themselves
    (mirrored from ``config/thresholds.yaml`` comments).

Implements V1_Engineering_Spec §11.3.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import yaml

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"


# ---------------------------------------------------------------------------
# Section dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class UnitAliasMap:
    """Layer 1 unit normalization table (canonical → set of aliases)."""

    canonical_to_aliases: Mapping[str, frozenset[str]]
    alias_to_canonical: Mapping[str, str]

    @classmethod
    def from_yaml(cls, data: Mapping[str, Any]) -> UnitAliasMap:
        canonical_to_aliases: dict[str, frozenset[str]] = {}
        alias_to_canonical: dict[str, str] = {}
        for canonical, payload in data.get("canonical_units", {}).items():
            aliases = frozenset(a.strip().lower() for a in payload.get("aliases", []))
            canonical_to_aliases[canonical] = aliases
            for alias in aliases:
                if alias in alias_to_canonical and alias_to_canonical[alias] != canonical:
                    raise ValueError(
                        f"Unit alias '{alias}' maps to both "
                        f"'{alias_to_canonical[alias]}' and '{canonical}' in unit_aliases.yaml"
                    )
                alias_to_canonical[alias] = canonical
            # Canonical form should also resolve to itself (lower-cased).
            alias_to_canonical.setdefault(canonical.lower(), canonical)
        return cls(canonical_to_aliases, alias_to_canonical)


@dataclass(frozen=True, slots=True)
class EncoderConfig:
    """Layer 3 [3a] encoder settings."""

    model_id: str
    dimension: int
    normalize: str
    batch_size: int
    device: str


@dataclass(frozen=True, slots=True)
class FaissConfig:
    """Layer 3 [3b] FAISS index settings."""

    index_type: str
    metric: str
    nlist: int
    nprobe: int
    top_k: int
    training_subset_size: int
    training_seed: int
    input_text_columns: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RuleEngineConfig:
    """Layer 2 confidence values + fuzzy threshold."""

    conf_exact_part_number: float
    conf_manufacturer_fuzzy: float
    conf_partial: float
    conf_no_match: float
    manufacturer_fuzzy_min_score: int


@dataclass(frozen=True, slots=True)
class ProductTypeConsensusConfig:
    """Layer 3 [3c] PT consensus bands."""

    band_high: float
    band_low: float


@dataclass(frozen=True, slots=True)
class ClusterConfig:
    """Layer 3 [3d] sample-bound config."""

    min_size: int
    low_sample_conf_cap: float


@dataclass(frozen=True, slots=True)
class FusionConfig:
    """Layer 4 fusion coefficients."""

    alpha: float
    pt_ambiguity_cap: float


@dataclass(frozen=True, slots=True)
class DecisionConfig:
    """Layer 4 routing thresholds."""

    auto_process: float
    human_review_floor: float


@dataclass(frozen=True, slots=True)
class OnlineUpdateConfig:
    """Layer 4 error-pushback coefficient."""

    pushback_lambda: float


@dataclass(frozen=True, slots=True)
class ThresholdsConfig:
    """All threshold-bearing sections collected for ergonomic access."""

    rule_engine: RuleEngineConfig
    product_type_consensus: ProductTypeConsensusConfig
    clusters: ClusterConfig
    fusion: FusionConfig
    decision: DecisionConfig
    online_updates: OnlineUpdateConfig


@dataclass(frozen=True, slots=True)
class CalibrationConfig:
    """Layer 4 σ calibration settings."""

    sigma_grid: tuple[float, ...]
    lambda_cal: float
    secondary_calibration_enabled: bool
    secondary_calibration_ocr_cache_path: str
    reliability_bins: int


@dataclass(frozen=True, slots=True)
class Settings:
    """Root settings object."""

    unit_aliases: UnitAliasMap
    encoder: EncoderConfig
    faiss: FaissConfig
    thresholds: ThresholdsConfig
    calibration: CalibrationConfig
    config_dir: Path = field(default_factory=lambda: CONFIG_DIR)


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def _read_yaml(path: Path) -> Mapping[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, Mapping):
        raise ValueError(f"{path} did not parse to a mapping at top level")
    return data


def load_settings(config_dir: Path = CONFIG_DIR) -> Settings:
    """Read all YAML files from ``config/`` and assemble a ``Settings``.

    Args:
        config_dir: Directory holding the five YAML files. Defaults to
            ``ML/Model/config/``.

    Raises:
        FileNotFoundError: If any expected YAML is missing.
        ValueError: If a YAML's shape doesn't match the dataclass schema.
    """

    unit_aliases = UnitAliasMap.from_yaml(_read_yaml(config_dir / "unit_aliases.yaml"))

    encoder_raw = _read_yaml(config_dir / "encoder.yaml")
    encoder = EncoderConfig(
        model_id=str(encoder_raw["model_id"]),
        dimension=int(encoder_raw["dimension"]),
        normalize=str(encoder_raw["normalize"]),
        batch_size=int(encoder_raw["batch_size"]),
        device=str(encoder_raw["device"]),
    )

    faiss_raw = _read_yaml(config_dir / "faiss.yaml")
    faiss = FaissConfig(
        index_type=str(faiss_raw["index_type"]),
        metric=str(faiss_raw["metric"]),
        nlist=int(faiss_raw["nlist"]),
        nprobe=int(faiss_raw["nprobe"]),
        top_k=int(faiss_raw["top_k"]),
        training_subset_size=int(faiss_raw["training_subset_size"]),
        training_seed=int(faiss_raw["training_seed"]),
        input_text_columns=tuple(str(c) for c in faiss_raw["input_text_columns"]),
    )

    th_raw = _read_yaml(config_dir / "thresholds.yaml")
    thresholds = ThresholdsConfig(
        rule_engine=RuleEngineConfig(
            conf_exact_part_number=float(th_raw["rule_engine"]["conf_exact_part_number"]),
            conf_manufacturer_fuzzy=float(th_raw["rule_engine"]["conf_manufacturer_fuzzy"]),
            conf_partial=float(th_raw["rule_engine"]["conf_partial"]),
            conf_no_match=float(th_raw["rule_engine"]["conf_no_match"]),
            manufacturer_fuzzy_min_score=int(th_raw["rule_engine"]["manufacturer_fuzzy_min_score"]),
        ),
        product_type_consensus=ProductTypeConsensusConfig(
            band_high=float(th_raw["product_type_consensus"]["band_high"]),
            band_low=float(th_raw["product_type_consensus"]["band_low"]),
        ),
        clusters=ClusterConfig(
            min_size=int(th_raw["clusters"]["min_size"]),
            low_sample_conf_cap=float(th_raw["clusters"]["low_sample_conf_cap"]),
        ),
        fusion=FusionConfig(
            alpha=float(th_raw["fusion"]["alpha"]),
            pt_ambiguity_cap=float(th_raw["fusion"]["pt_ambiguity_cap"]),
        ),
        decision=DecisionConfig(
            auto_process=float(th_raw["decision"]["auto_process"]),
            human_review_floor=float(th_raw["decision"]["human_review_floor"]),
        ),
        online_updates=OnlineUpdateConfig(
            pushback_lambda=float(th_raw["online_updates"]["pushback_lambda"]),
        ),
    )

    cal_raw = _read_yaml(config_dir / "calibration.yaml")
    calibration = CalibrationConfig(
        sigma_grid=tuple(float(s) for s in cal_raw["sigma_grid"]),
        lambda_cal=float(cal_raw["lambda_cal"]),
        secondary_calibration_enabled=bool(cal_raw["secondary_calibration"]["enabled"]),
        secondary_calibration_ocr_cache_path=str(cal_raw["secondary_calibration"]["ocr_cache_path"]),
        reliability_bins=int(cal_raw["reliability_bins"]),
    )

    return Settings(
        unit_aliases=unit_aliases,
        encoder=encoder,
        faiss=faiss,
        thresholds=thresholds,
        calibration=calibration,
        config_dir=config_dir,
    )


@lru_cache(maxsize=1)
def default_settings() -> Settings:
    """Cached default-path ``load_settings()`` for convenience in scripts.

    Tests and library code should pass a freshly built ``Settings`` via
    constructor injection instead of relying on this cache.
    """
    return load_settings()
