"""D28 guard tests that scan the whole repo, not a directory that happened to exist at T1."""

import ast
from pathlib import Path

SKIP_DIRS = {".git", ".venv", "tests", "__pycache__", "docs", "reports", "results", "data"}


def _py_files(root: Path):
    for p in root.rglob("*.py"):
        if not (set(p.relative_to(root).parts) & SKIP_DIRS):
            yield p


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_qdrant_client_only_in_store(repo_root: Path):
    """D-002: the Qdrant client is constructed in exactly one place."""
    allowed = repo_root / "ledger" / "retrieval" / "store.py"
    offenders = [
        p for p in _py_files(repo_root) if p != allowed and "QdrantClient" in p.read_text("utf-8")
    ]
    assert not offenders, f"QdrantClient referenced outside retrieval/store.py: {offenders}"


def test_no_phoenix_import_anywhere(repo_root: Path):
    """D-017: evaluation transport is OpenInference over OTLP; no module imports phoenix."""
    offenders = [p for p in _py_files(repo_root) if "phoenix" in _imports(p)]
    assert not offenders, f"phoenix imported by: {offenders}"


def test_no_top_level_ledger_module(repo_root: Path):
    """Naming rule: the claim ledger is ledger/claims/ledger.py; ledger/ledger.py must not exist."""
    assert not (repo_root / "ledger" / "ledger.py").exists()
    assert (repo_root / "ledger" / "claims" / "ledger.py").exists()


def test_endpoint_not_hardcoded(repo_root: Path):
    """D-014: the OTLP endpoint comes from the environment only."""
    src = (repo_root / "ledger" / "tracing" / "otel.py").read_text("utf-8")
    assert "http://" not in src and "https://" not in src
    assert "OTEL_EXPORTER_OTLP_ENDPOINT" in src
