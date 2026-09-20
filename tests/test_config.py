from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from ledger.config import Config, load_config


def test_base_config_loads(base_config_path: Path):
    cfg = load_config(base_config_path)
    assert cfg.verifier.precision == "bf16"
    assert cfg.chunking.max_tokens == 512
    assert cfg.paths.chunk_ids_lock == Path("data/chunk_ids.lock")
    assert not hasattr(cfg.tracing, "endpoint")  # D-014: env only


def _mutated(base_config_path: Path, section: str, key: str, value):
    data = yaml.safe_load(base_config_path.read_text("utf-8"))
    data[section][key] = value
    return data


def test_verifier_precision_must_be_bf16(base_config_path: Path):
    """D-012."""
    with pytest.raises(ValidationError, match="bf16"):
        Config.model_validate(_mutated(base_config_path, "verifier", "precision", "fp16"))
    with pytest.raises(ValidationError, match="bf16"):
        Config.model_validate(_mutated(base_config_path, "verifier", "precision", "awq-int4"))


@pytest.mark.parametrize("key", ["temperature", "top_p", "top_k"])
def test_sampling_parameters_rejected_explicitly(base_config_path: Path, key: str):
    """D-019: the message must name the decision and say the API removed the parameter."""
    with pytest.raises(ValidationError, match=r"D-019.*removed from the Claude API"):
        Config.model_validate(_mutated(base_config_path, "generator", key, 0.3))
    # anywhere in the tree, not just under generator
    with pytest.raises(ValidationError, match="D-019"):
        Config.model_validate(_mutated(base_config_path, "questions", key, 0.3))


def test_base_config_has_no_sampling_keys(base_config_path: Path):
    text = base_config_path.read_text("utf-8")
    for key in ("temperature:", "top_p:", "top_k:"):
        assert key not in text


@pytest.mark.parametrize(
    ("key", "bad"),
    [("repeat_table_header", False), ("omit_header_on_overflow", True), ("merge_peers", True)],
)
def test_chunker_switches_pinned(base_config_path: Path, key: str, bad: bool):
    """D-033: the three HybridChunker switches are pinned with explicit messages."""
    with pytest.raises(ValidationError, match="D-033"):
        Config.model_validate(_mutated(base_config_path, "chunking", key, bad))


def test_tables_atomic_key_is_gone(base_config_path: Path):
    """D-033: the switch the library never had is not a config key."""
    with pytest.raises(ValidationError):
        Config.model_validate(_mutated(base_config_path, "chunking", "tables_atomic", True))


def test_unknown_key_rejected(base_config_path: Path):
    with pytest.raises(ValidationError):
        Config.model_validate(_mutated(base_config_path, "loop", "max_iters_typo", 3))


def test_judge_requires_pinned_revision(base_config_path: Path):
    """D-007: config loads with an empty judge, the judge loader raises."""
    cfg = load_config(base_config_path)
    with pytest.raises(RuntimeError, match="D-007"):
        cfg.judge.require_pinned()


def test_override_deep_merges(base_config_path: Path, tmp_path: Path):
    override = tmp_path / "o.yaml"
    override.write_text("retrieval:\n  k_final: 8\n", encoding="utf-8")
    cfg = load_config(base_config_path, override)
    assert cfg.retrieval.k_final == 8
    assert cfg.retrieval.k_dense == 30  # untouched sibling survives
