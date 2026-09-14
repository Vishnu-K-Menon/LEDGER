"""Shared fixtures. Tests run from the repo root (pyproject ``testpaths``)."""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def base_config_path(repo_root: Path) -> Path:
    return repo_root / "configs" / "base.yaml"
