"""Vector store access. D-002: the Qdrant client is constructed in exactly one place — here —
behind ``vector_store.mode``. Nothing else may import ``QdrantClient``; ``tests/test_guards.py``
scans the repo for the name. Body arrives with T4."""

from ledger.config import Config


def make_client(cfg: Config):
    """Return the single Qdrant client for ``cfg.vector_store.mode`` (local file in v1)."""
    raise NotImplementedError("make_client is built in T4 (D-002)")
