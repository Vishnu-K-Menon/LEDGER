"""Offline twins of the tokenizer-agnostic T3 logic tests (D-028). A whitespace tokenizer stands in
for the Qwen3 embedder tokenizer, so these run with no network and no Hugging Face cache. They add
to, and never replace, the real-tokenizer tests in test_parse.py / test_d037.py (marker
``needs_hf_tokenizer``); token-count assertions stay with the real tokenizer."""

from __future__ import annotations

from typing import Any

import pytest
from docling_core.transforms.chunker.tokenizer.base import BaseTokenizer
from test_parse import _doc_with_table, _row

from ledger.config import load_config
from ledger.ingest import parse as parse_mod
from ledger.ingest.parse import build_chunker, chunk_records

pytestmark = pytest.mark.parse


class WhitespaceTokenizer(BaseTokenizer):
    """One token per whitespace-separated word (synthetic; not the embedder's vocabulary)."""

    max_tokens: int = 512

    def count_tokens(self, text: str) -> int:
        return len(text.split())

    def get_max_tokens(self) -> int:
        return self.max_tokens

    def get_tokenizer(self) -> Any:
        return self


@pytest.fixture(scope="module", params=[False, True], ids=["padded", "compact"])
def synth_cfg(base_config_path, request):
    base = load_config(base_config_path)
    return base.model_copy(
        update={
            "chunking": base.chunking.model_copy(update={"markdown_compact_tables": request.param})
        }
    )


@pytest.fixture
def synth_chunker(synth_cfg, monkeypatch):
    monkeypatch.setattr(
        parse_mod.HuggingFaceTokenizer,
        "from_pretrained",
        classmethod(
            lambda cls, model_name, max_tokens, **k: WhitespaceTokenizer(max_tokens=max_tokens)
        ),
    )
    return build_chunker(synth_cfg)


def test_synthetic_no_chunk_mixes_table_and_prose(synth_chunker, synth_cfg):
    doc = _doc_with_table("mix", rows=6)
    recs = chunk_records(
        _row("s1"), list(synth_chunker.chunk(dl_doc=doc)), synth_chunker, synth_cfg
    )
    assert recs
    assert not any(r["mixed_items"] for r in recs)
    assert {r["chunk_type"] for r in recs} <= {"table", "prose"}
    assert any(r["chunk_type"] == "table" for r in recs)


def test_synthetic_chunk_ids_stable_and_slice_indexed(synth_chunker, synth_cfg):
    doc = _doc_with_table("ids", rows=400)
    first = chunk_records(
        _row("s4"), list(synth_chunker.chunk(dl_doc=doc)), synth_chunker, synth_cfg
    )
    again = chunk_records(
        _row("s4"), list(synth_chunker.chunk(dl_doc=doc)), synth_chunker, synth_cfg
    )
    other = chunk_records(
        _row("s5"),
        list(synth_chunker.chunk(dl_doc=_doc_with_table("x", 8))),
        synth_chunker,
        synth_cfg,
    )
    assert [r["chunk_id"] for r in first] == [r["chunk_id"] for r in again]
    assert all(r["chunk_id"].startswith("s4::p") for r in first)
    assert all(r["chunk_id"].startswith("s5::p") for r in other)
    slices = [r["slice"] for r in first if r["chunk_type"] == "table"]
    assert len(slices) > 1 and slices == sorted(slices) and slices[0] == 0
