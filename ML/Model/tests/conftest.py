"""Shared pytest fixtures."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.config import Settings, load_settings


@pytest.fixture(scope="session")
def settings() -> Settings:
    """Real configuration loaded from ``config/`` once per session."""
    return load_settings()


@pytest.fixture(scope="session")
def aliases(settings: Settings):
    """Unit-alias map convenience handle.

    Retained even though Layer 1 has been handed off — the canonical
    unit forms in ``config/unit_aliases.yaml`` are the reference the
    extraction team aligns to, and downstream consumers may still need
    the map (e.g. to validate that incoming ``normalized_units`` use
    canonical strings).
    """
    return settings.unit_aliases


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    return Path(__file__).resolve().parent / "fixtures"
