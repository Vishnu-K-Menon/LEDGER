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


# ---- offline gate (D-028) -----------------------------------------------------------------
# Tests that build the real embedder tokenizer (``build_chunker`` -> Hugging Face) carry the
# ``needs_hf_tokenizer`` marker and skip cleanly when it is not cached (HF_HUB_OFFLINE=1 in CI).
# Any test requesting the ``chunker`` fixture is marked automatically.

NEEDS_TOKENIZER = "needs_hf_tokenizer"


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        f"{NEEDS_TOKENIZER}: needs the real Qwen3 embedder tokenizer in the Hugging Face cache; "
        "skipped when it is not cached",
    )


def _tokenizer_cached() -> bool:
    try:
        from huggingface_hub import try_to_load_from_cache

        from ledger.config import load_config

        model = load_config(REPO_ROOT / "configs" / "base.yaml").embedding.model
        path = try_to_load_from_cache(model, "tokenizer.json")
        return isinstance(path, str)
    except Exception:
        return False


def pytest_collection_modifyitems(config, items):
    cached = None
    for item in items:
        if "chunker" in getattr(item, "fixturenames", ()):
            item.add_marker(getattr(pytest.mark, NEEDS_TOKENIZER))
        if item.get_closest_marker(NEEDS_TOKENIZER) is None:
            continue
        if cached is None:
            cached = _tokenizer_cached()
        if not cached:
            item.add_marker(
                pytest.mark.skip(
                    reason="embedder (Qwen3) tokenizer not in the Hugging Face cache "
                    "(offline); needs the real tokenizer"
                )
            )
