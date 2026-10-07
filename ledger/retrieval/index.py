"""``ledger index`` (T4): embed the ingested chunks, build the Qdrant file, freeze the chunk IDs.

* D-032 status 2026-10-07: ``data/chunk_ids.lock`` freezes chunk IDs and each chunk's text
  (sha256) and nothing else. Written once, never rewritten. The index is derived from the locked
  chunks and may be rebuilt only when every id and text hash equals the lock. Index facts
  (model, revision, dim) live beside the index in ``data/index_meta.json``.
* D-040: chunks of EXCLUDED units must not appear; D-037 status 2026-10-06: no U+0008 in any text.
* There is no ``--force`` in either direction.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from ledger.config import Config
from ledger.ingest.manifest import ManifestRow, active_rows, read_manifest
from ledger.retrieval import store

LOCK_HEADER = "# ledger chunk_ids.lock v1"
BACKSPACE = "\x08"  # U+0008


class IndexRefused(RuntimeError):
    """The run must not proceed; the message lists the offenders."""


# ---- hashing --------------------------------------------------------------------------------


def lf_sha256(path: Path) -> str:
    """sha256 of the file bytes with CRLF normalised to LF, so a Windows checkout and a Linux
    one hash alike."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_chunks(path: Path) -> list[dict[str, Any]]:
    """Chunk records in file order (the order is part of the lock)."""
    out = []
    with path.open("r", encoding="utf-8", newline="") as fh:
        for line in fh:
            if line.strip():
                out.append(json.loads(line))
    return out


# ---- input checks (no GPU, writes nothing) --------------------------------------------------


@dataclass
class InputReport:
    active_without_chunks: list[str] = field(default_factory=list)
    unit_not_active: list[str] = field(default_factory=list)
    duplicate_chunk_id: list[str] = field(default_factory=list)
    bad_id_prefix: list[str] = field(default_factory=list)
    backspace_in_text: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(len(v) for v in self.counts().values())

    def counts(self) -> dict[str, list[str]]:
        return {
            "active_row_without_chunks": self.active_without_chunks,
            "chunk_unit_not_active": self.unit_not_active,
            "duplicate_chunk_id": self.duplicate_chunk_id,
            "chunk_id_without_unit_prefix": self.bad_id_prefix,
            "u0008_in_text": self.backspace_in_text,
        }

    def render(self, limit: int = 10) -> str:
        lines = []
        for name, offenders in self.counts().items():
            lines.append(f"{name}: {len(offenders)}")
            lines.extend(f"    {o}" for o in offenders[:limit])
            if len(offenders) > limit:
                lines.append(f"    ... and {len(offenders) - limit} more")
        return "\n".join(lines)


def check_inputs(chunks: Sequence[Mapping[str, Any]], rows: Sequence[ManifestRow]) -> InputReport:
    """The refuse conditions. Pure: no GPU, no Qdrant, nothing written."""
    rep = InputReport()
    active = active_rows(list(rows))
    active_ids = {r.unit_id for r in active}
    have_chunks = {c["unit_id"] for c in chunks}
    for r in active:
        # same test as ledger/ingest/parse.py (T3): an UNFETCHABLE row legitimately has no chunks
        unfetchable = any("UNFETCHABLE" in n for n in r.notes)
        if r.unit_id not in have_chunks and not unfetchable:
            rep.active_without_chunks.append(r.unit_id)
    seen: set[str] = set()
    dup: set[str] = set()
    for c in chunks:
        cid, uid = c["chunk_id"], c["unit_id"]
        if uid not in active_ids:
            rep.unit_not_active.append(cid)
        if cid in seen and cid not in dup:
            dup.add(cid)
            rep.duplicate_chunk_id.append(cid)
        seen.add(cid)
        if not cid.startswith(f"{uid}::"):
            rep.bad_id_prefix.append(cid)
        if BACKSPACE in c["text"]:
            rep.backspace_in_text.append(cid)
    return rep


# ---- the lock -------------------------------------------------------------------------------


def render_lock(
    chunks: Sequence[Mapping[str, Any]],
    *,
    chunks_sha256: str,
    manifest_sha256: str,
    git_commit: str | None,
    created_utc: str,
) -> str:
    """LF text, UTF-8: a ``#`` header, then ``chunk_id<TAB>sha256(text)`` per chunk in
    chunks.jsonl order. Nothing about the model or config (D-032 status 2026-10-07)."""
    head = [
        LOCK_HEADER,
        f"# records: {len(chunks)}",
        f"# chunks_jsonl_sha256 (CRLF->LF): {chunks_sha256}",
        f"# manifest_jsonl_sha256 (CRLF->LF): {manifest_sha256}",
        f"# git_commit: {git_commit or 'unavailable'}",
        f"# created_utc: {created_utc}",
    ]
    body = [f"{c['chunk_id']}\t{text_sha256(c['text'])}" for c in chunks]
    return "\n".join(head + body) + "\n"


def parse_lock(text: str) -> tuple[dict[str, str], list[tuple[str, str]]]:
    header: dict[str, str] = {}
    entries: list[tuple[str, str]] = []
    for line in text.split("\n"):
        if not line:
            continue
        if line.startswith("#"):
            key, _, val = line[1:].partition(":")
            header[key.strip()] = val.strip()
        else:
            cid, _, sha = line.partition("\t")
            entries.append((cid, sha))
    return header, entries


def read_lock(path: Path) -> tuple[dict[str, str], list[tuple[str, str]]]:
    return parse_lock(path.read_bytes().decode("utf-8"))


def compare_to_lock(
    chunks: Sequence[Mapping[str, Any]], entries: Sequence[tuple[str, str]]
) -> list[str]:
    """Every id and text hash, in order. Returns one line per difference (all of them)."""
    diffs = []
    for i in range(max(len(chunks), len(entries))):
        now = (chunks[i]["chunk_id"], text_sha256(chunks[i]["text"])) if i < len(chunks) else None
        locked = entries[i] if i < len(entries) else None
        if now != locked:
            diffs.append(f"position {i}: locked={_short(locked)} now={_short(now)}")
    return diffs


def _short(e: tuple[str, str] | None) -> str:
    return "<absent>" if e is None else f"{e[0]} sha256={e[1][:12]}"


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


# ---- embedder -------------------------------------------------------------------------------


class Embedder(Protocol):
    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    def info(self) -> dict[str, Any]:
        """model, revision, precision, torch/transformers versions, gpu, max_tokens, truncations
        — read after ``embed_documents``."""
        ...


class Qwen3Embedder:
    """Qwen3-Embedding-4B, bf16, from the model card (README.md at the pinned revision, "Usage",
    Transformers example):

    * pooling: last token (``1_Pooling/config.json``: ``pooling_mode_lasttoken`` true), taken at
      position -1 because the tokenizer is built with ``padding_side="left"``;
    * the tokenizer appends ``<|endoftext|>`` (id 151643) to every input, so the last token is
      that end marker (checked below — the pooled position must be it);
    * L2-normalised (``F.normalize(p=2)``); cosine in the store then equals dot product;
    * documents take no instruction (card: "No need to add instruction for retrieval documents");
      queries use ``Instruct: {task}\\nQuery:{query}`` (``embedding.query_instruction``, T5).
    """

    def __init__(self, cfg: Config):
        import torch
        import transformers
        from transformers import AutoModel, AutoTokenizer

        e = cfg.embedding
        self._torch = torch
        self.model_id, self.revision, self.precision = e.model, e.revision, e.precision
        self.max_length, self.batch_tokens = e.max_length, e.batch_tokens
        self.tok = AutoTokenizer.from_pretrained(e.model, revision=e.revision, padding_side="left")
        self.model = (
            AutoModel.from_pretrained(e.model, revision=e.revision, dtype=torch.bfloat16)
            .to("cuda")
            .eval()
        )
        if next(self.model.parameters()).dtype != torch.bfloat16:
            raise IndexRefused("embedder did not load as bf16 (D-012)")
        self._versions = {"torch": torch.__version__, "transformers": transformers.__version__}
        self.max_tokens_embedded = 0
        self.truncations = 0

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        torch = self._torch
        f = torch.nn.functional
        # untruncated lengths: truncation is counted, never silent
        lengths = [len(ids) for ids in self.tok(list(texts), truncation=False)["input_ids"]]
        self.truncations = sum(n > self.max_length for n in lengths)
        self.max_tokens_embedded = max(min(n, self.max_length) for n in lengths)
        order = sorted(range(len(texts)), key=lambda i: lengths[i], reverse=True)
        out: list[list[float] | None] = [None] * len(texts)
        i = 0
        while i < len(order):
            width = min(lengths[order[i]], self.max_length)  # longest first
            n = max(1, self.batch_tokens // max(width, 1))
            idx = order[i : i + n]
            i += n
            batch = self.tok(
                [texts[j] for j in idx],
                padding=True,
                truncation=True,
                max_length=self.max_length,
                return_tensors="pt",
            ).to("cuda")
            with torch.no_grad():
                hidden = self.model(**batch).last_hidden_state
            pooled = f.normalize(hidden[:, -1], p=2, dim=1).float().cpu()
            untruncated = [lengths[j] <= self.max_length for j in idx]
            last = batch["input_ids"][:, -1].cpu().tolist()
            for k, ok in enumerate(untruncated):
                if ok and last[k] != self.tok.pad_token_id:
                    raise IndexRefused(
                        f"pooled position is not the end marker for {texts[idx[k]][:40]!r}"
                    )
            for j, vec in zip(idx, pooled.tolist(), strict=True):
                out[j] = vec
        return out  # type: ignore[return-value]

    def info(self) -> dict[str, Any]:
        return {
            "model": self.model_id,
            "revision": self.revision,
            "precision": self.precision,
            **self._versions,
            "gpu": self._torch.cuda.get_device_name(0),
            "max_tokens_embedded": self.max_tokens_embedded,
            "truncations": self.truncations,
        }


# ---- the run --------------------------------------------------------------------------------


def git_commit(repo: Path) -> str | None:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() or None if r.returncode == 0 else None


def config_hash(cfg: Config) -> str:
    blob = json.dumps(cfg.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_index(cfg: Config, repo: Path, embedder: Embedder) -> dict[str, Any]:
    """Run the index build; returns the ``index_meta`` dict. Raises ``IndexRefused``."""
    t0 = time.monotonic()
    chunks_path, manifest_path = repo / cfg.paths.chunks, repo / cfg.paths.manifest
    lock_path = repo / cfg.paths.chunk_ids_lock
    meta_path = lock_path.with_name("index_meta.json")

    chunks = read_chunks(chunks_path)
    _, rows = read_manifest(manifest_path)
    report = check_inputs(chunks, rows)
    if not report.ok:
        raise IndexRefused("input checks failed:\n" + report.render())

    lock_present = lock_path.exists()
    if lock_present:
        _, entries = read_lock(lock_path)
        diffs = compare_to_lock(chunks, entries)
        if diffs:
            raise IndexRefused(
                f"chunks differ from {lock_path.name} ({len(diffs)} differences; first 10):\n"
                + "\n".join(diffs[:10])
            )

    vectors = embedder.embed_documents([c["text"] for c in chunks])
    if len(vectors) != len(chunks) or any(len(v) != cfg.embedding.dim for v in vectors):
        got = sorted({len(v) for v in vectors})
        raise IndexRefused(f"embedding dim {got} != embedding.dim {cfg.embedding.dim}")

    client = store.make_client(cfg, repo=repo)
    try:
        store.recreate_collection(client, cfg)
        store.upsert_points(client, cfg, chunks, vectors)
        name = cfg.vector_store.collection
        count = client.count(collection_name=name, exact=True).count
        if count != len(chunks):
            raise IndexRefused(f"point count {count} != {len(chunks)} records")
        active_ids = {r.unit_id for r in active_rows(rows)}
        units: set[str] = set()
        offset = None
        while True:
            pts, offset = client.scroll(
                collection_name=name, limit=1000, offset=offset, with_payload=["unit_id"]
            )
            units.update(p.payload["unit_id"] for p in pts)
            if offset is None:
                break
        excluded = sorted(units - active_ids)
        if excluded:
            raise IndexRefused(f"payload rows belong to non-active units: {excluded}")
    finally:
        client.close()

    now = _utc_now()
    info = embedder.info()
    meta = {
        "embedding": {
            "model": info.get("model"),
            "revision": info.get("revision"),
            "dim": cfg.embedding.dim,
            "precision": info.get("precision"),
        },
        "point_id_scheme": store.POINT_ID_SCHEME,
        "torch": info.get("torch"),
        "transformers": info.get("transformers"),
        "gpu": info.get("gpu"),
        "max_tokens_embedded": info.get("max_tokens_embedded"),
        "truncations": info.get("truncations"),
        "point_count": count,
        "collection": cfg.vector_store.collection,
        "config_hash": config_hash(cfg),
        "git_commit": git_commit(repo),
        "created_utc": now,
        "seconds": round(time.monotonic() - t0, 1),
        "lock_written": not lock_present,
    }
    _atomic_write(meta_path, json.dumps(meta, indent=2) + "\n")
    if not lock_present:  # last, and only once
        _atomic_write(
            lock_path,
            render_lock(
                chunks,
                chunks_sha256=lf_sha256(chunks_path),
                manifest_sha256=lf_sha256(manifest_path),
                git_commit=meta["git_commit"],
                created_utc=now,
            ),
        )
    return meta


def run_index(cfg: Config, repo: Path) -> int:
    """CLI body. CUDA is checked before anything under ``data/`` is read or written; the CLI
    never runs on CPU."""
    import torch

    from ledger.tracing import otel

    if not torch.cuda.is_available():
        print("ledger index: CUDA is not available; refusing (the CLI never runs on CPU).")
        return 2
    otel.init_tracing(cfg)
    code = 0
    try:
        with otel.run_span("ledger.index", {"rag.record_type": "index_run"}) as span:
            trace_id, _ = otel.ids_of(span)
            print(f"trace id: {trace_id}")
            print(f"{otel.ENDPOINT_ENV} set: {bool(os.environ.get(otel.ENDPOINT_ENV))}")
            try:
                meta = build_index(cfg, repo, Qwen3Embedder(cfg))
            except IndexRefused as e:
                print(f"ledger index: refused.\n{e}")
                code = 1
            else:
                span.set_attribute("index.point_count", meta["point_count"])
                print(json.dumps(meta, indent=2))
    finally:
        otel.shutdown_tracing()
    return code
