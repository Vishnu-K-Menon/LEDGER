"""D-037 status 2026-10-06 (item 5 extended): leader runs go from every table body cell, with a
U+0008 in the same cell before a removed run. Synthetic records, a fake tokenizer: no network, no
Hugging Face cache, nothing under data/."""

from __future__ import annotations

from types import SimpleNamespace

from ledger.ingest.parse import strip_leader_runs

F = "�"
BS = "\x08"
SEP = "| --- | --- | --- |"
HEADER = f"| Item | Label{F}{F} | Value |"
PREFIX = "[In millions of dollars]\nSection 1\n"


class _Tok:
    def count_tokens(self, text: str) -> int:
        return len(text.split())


CHUNKER = SimpleNamespace(tokenizer=_Tok())


def _rec(rows: list[str], *, chunk_type: str = "table") -> dict:
    body = "\n".join([HEADER, SEP, *rows]) + "\n"
    return {
        "chunk_id": "u::p1::tbl-0::s0",
        "chunk_type": chunk_type,
        "text": PREFIX + body,
        "body_chars": len(body),
        "n_tokens": 1,
        "slice": 0,
    }


def _body(rec: dict) -> str:
    return rec["text"][len(rec["text"]) - rec["body_chars"] :]


def test_run_in_cell_2_is_removed_with_its_backspace_with_and_without_a_space():
    rows = [
        f"| 1 | Opportunity Zones {BS}{F * 30} | 3,080 |",
        f"| 2 | Credit {BS} {F * 9} | 7 |",
        f"| 3 | Third{BS}{F * 2} | 8 |",
    ]
    (rec,) = strip_leader_runs([_rec(rows)], CHUNKER)
    body = _body(rec)
    assert F * 2 not in body.split(SEP)[1] and BS not in body
    assert "| 1 | Opportunity Zones  | 3,080 |" in body
    assert "| 2 | Credit  | 7 |" in body
    assert "| 3 | Third | 8 |" in body
    assert rec["fffd_removed"] == 30 + 9 + 2 and rec["u0008_removed"] == 3


def test_header_single_lone_backspace_and_other_cells_are_untouched():
    rows = [
        f"| 1 | Lone {BS} backspace | 3 |",  # a U+0008 not before a run
        f"| 2 | one {F} only | 5{F}6 |",  # single U+FFFD, kept
        f"| 3 | cell {BS} | {F * 4} |",  # U+0008 in one cell, the run in ANOTHER cell
    ]
    (rec,) = strip_leader_runs([_rec(rows)], CHUNKER)
    body = _body(rec)
    assert body.startswith(HEADER)  # header-row run untouched
    assert f"Lone {BS} backspace" in body and f"one {F} only" in body and f"5{F}6" in body
    assert f"cell {BS} |" in body  # backspace kept: the run is not in its cell
    assert rec["fffd_removed"] == 4 and "u0008_removed" not in rec  # only the value-cell run


def test_ids_and_other_fields_unchanged_sizes_recomputed_and_idempotent():
    rows = [f"| 1 | Label {BS}{F * 12} | 3 |"]
    before = _rec(rows)
    (after,) = strip_leader_runs([before], CHUNKER)
    for k in ("chunk_id", "chunk_type", "slice"):
        assert after[k] == before[k]
    assert after["text"].startswith(PREFIX)  # prefix / heading lines byte-identical
    assert after["body_chars"] == len(_body(after)) < before["body_chars"]
    assert after["n_tokens"] == CHUNKER.tokenizer.count_tokens(after["text"])
    again = strip_leader_runs([after], CHUNKER)
    assert again == [{**after, "fffd_removed": 0}]  # second pass removes nothing


def test_prose_and_untouched_table_records_pass_through():
    prose = {"chunk_type": "prose", "text": f"a {BS}{F * 5} b", "body_chars": 8}
    assert strip_leader_runs([prose], CHUNKER) == [prose]
    clean = _rec(["| 1 | fine | 2 |"])
    (out,) = strip_leader_runs([clean], CHUNKER)
    assert out["text"] == clean["text"] and out["n_tokens"] == clean["n_tokens"]
    assert out["fffd_removed"] == 0 and "u0008_removed" not in out
