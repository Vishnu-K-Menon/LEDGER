"""Vector store access. D-002: the Qdrant client is constructed in exactly one place — here —
behind ``vector_store.mode``. Nothing else may import the client class; ``tests/test_guards.py``
scans the repo for its name.

Collection layout (D5): one dense named vector (``dim`` from config, cosine) and one sparse named
vector for BM25, declared at creation and left empty (``vector_store.sparse_enabled`` false in v1).
Point ids are ``uuid5(NAMESPACE, chunk_id)``: the store rejects string ids, and a positional id
would be a global counter, which D-032 forbids (ingesting later documents must not renumber
earlier ones). Payload indexes are not created: in local mode they have no effect.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient, models

from ledger.config import Config

DENSE_VECTOR = "dense"
SPARSE_VECTOR = "bm25"
# Defined once. Changing it renumbers every point, so it is part of the index's identity
# (recorded in data/index_meta.json as the point-id scheme).
POINT_ID_NAMESPACE = uuid.UUID("5f0c4f58-6c1e-5d0e-9a53-1e5d6a0b7d11")
POINT_ID_SCHEME = f"uuid5({POINT_ID_NAMESPACE}, chunk_id)"


def make_client(cfg: Config, *, repo: Path | None = None) -> QdrantClient:
    """Return the single Qdrant client for ``cfg.vector_store.mode`` (local file in v1).

    Local (embedded) mode takes an exclusive lock on the folder: one process at a time."""
    mode = cfg.vector_store.mode
    if mode == "local":
        path = (repo or Path.cwd()) / cfg.paths.qdrant_path
        path.parent.mkdir(parents=True, exist_ok=True)
        return QdrantClient(path=str(path))
    raise NotImplementedError(f"vector_store.mode={mode!r} is v2 (D-002)")


def point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(POINT_ID_NAMESPACE, chunk_id))


def payload_of(record: Mapping[str, Any]) -> dict[str, Any]:
    """Payload for one chunk record. ``unit_id`` is D5's ``doc_id`` (no ``doc_id`` field exists
    in the records). ``is_table`` follows ``chunk_type`` (D-036)."""
    bar = record.get("question_source_barred") or {}
    return {
        "chunk_id": record["chunk_id"],
        "unit_id": record["unit_id"],
        "source": record["source"],
        "parent_series": record["parent_series"],
        "chunk_type": record["chunk_type"],
        "is_table": record["chunk_type"] == "table",
        "page": record["page"],
        "question_source_barred": bool(bar.get("barred", False)),
        "question_source_barred_reasons": list(bar.get("reasons", [])),
        "parse_path": record.get("parse_path"),
    }


def recreate_collection(client: QdrantClient, cfg: Config) -> None:
    """Drop and recreate the collection, so a rerun after a failed run starts clean."""
    name = cfg.vector_store.collection
    if client.collection_exists(name):
        client.delete_collection(name)
    client.create_collection(
        collection_name=name,
        vectors_config={
            DENSE_VECTOR: models.VectorParams(
                size=cfg.embedding.dim, distance=models.Distance.COSINE
            )
        },
        sparse_vectors_config={SPARSE_VECTOR: models.SparseVectorParams()},
    )


def upsert_points(
    client: QdrantClient,
    cfg: Config,
    records: list[Mapping[str, Any]],
    vectors: list[list[float]],
    *,
    batch: int = 256,
) -> None:
    name = cfg.vector_store.collection
    for i in range(0, len(records), batch):
        pts = [
            models.PointStruct(
                id=point_id(r["chunk_id"]),
                vector={DENSE_VECTOR: v},
                payload=payload_of(r),
            )
            for r, v in zip(records[i : i + batch], vectors[i : i + batch], strict=True)
        ]
        client.upsert(collection_name=name, points=pts)


def dense_search(
    client: QdrantClient, cfg: Config, vector: list[float], k: int
) -> list[tuple[str, float]]:
    """Top-``k`` ``(chunk_id, cosine score)`` by the dense named vector, best first. The payload
    holds ids only; texts come from ``data/chunks.jsonl``, checked against the lock."""
    res = client.query_points(
        collection_name=cfg.vector_store.collection,
        query=vector,
        using=DENSE_VECTOR,
        limit=k,
        with_payload=["chunk_id"],
    )
    return [(p.payload["chunk_id"], float(p.score)) for p in res.points]
