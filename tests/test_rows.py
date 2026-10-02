"""The text-layer row fix (ledger/ingest/rows.py; D-038 rung 1, D-039 rung 1b production port).

Parity with the frozen emitter is gated by ``scripts/a1_diag/rung1b/port_parity.py`` on the local
data (byte-identical on 19 pilot + 16 fresh units, 77 burned tables, 704 BUDGET/CBO pins); these
are the synthetic unit tests D-038 names: a no-leading table whose rows TableFormer merged, the
header assertion, and BUDGET/CBO passing through untouched."""

from __future__ import annotations

import ast
import copy
from pathlib import Path

from ledger.config import load_config
from ledger.ingest import rows

P = load_config().parser.row_fix
SIZE = 6.6  # MER's no-leading body size


def chars(word: str, x0: float, top: float, size: float = SIZE) -> list[dict]:
    w = 0.5 * size
    return [
        {
            "text": ch,
            "x0": x0 + i * w,
            "x1": x0 + (i + 1) * w,
            "top": top,
            "bottom": top + size,
            "size": size,
        }
        for i, ch in enumerate(word)
    ]


def line(top: float, *words: tuple[str, float]) -> list[dict]:
    out: list[dict] = []
    for i, (word, x0) in enumerate(words):
        if i:
            out.append(
                {
                    "text": " ",
                    "x0": x0 - 1,
                    "x1": x0,
                    "top": top,
                    "bottom": top + SIZE,
                    "size": SIZE,
                }
            )
        out += chars(word, x0, top)
    return out


class _Page:
    def __init__(self, cs: list[dict]) -> None:
        self.chars = cs


class _Pdf:
    def __init__(self, cs: list[dict]) -> None:
        self.pages = [_Page(cs)]


def tf_cell(text, r, c, *, header=False, bbox=None) -> dict:
    return {
        "text": text,
        "start_row_offset_idx": r,
        "end_row_offset_idx": r + 1,
        "start_col_offset_idx": c,
        "end_col_offset_idx": c + 1,
        "column_header": header,
        "row_header": False,
        "bbox": bbox,
    }


def merged_doc() -> tuple[dict, list[dict]]:
    """A no-leading 3-row table; TableFormer merged rows 2021 and 2022 into one row."""
    page = (
        line(10, ("Year", 10), ("Coal", 60), ("Gas", 100))
        + line(20, ("2020", 10), ("1.5", 62), ("2.5", 100))
        + line(27, ("2021", 10), ("3.5", 62), ("4.5", 100))
        + line(34, ("2022", 10), ("5.5", 62), ("6.5", 100))
    )
    b1, b2 = {"l": 60, "r": 72, "t": 20, "b": 40}, {"l": 98, "r": 110, "t": 20, "b": 40}
    cells = [
        tf_cell("Year", 0, 0, header=True),
        tf_cell("Coal", 0, 1, header=True),
        tf_cell("Gas", 0, 2, header=True),
        tf_cell("2020", 1, 0),
        tf_cell("1.5", 1, 1, bbox=b1),
        tf_cell("2.5", 1, 2, bbox=b2),
        tf_cell("2021 2022", 2, 0),
        tf_cell("3.5 5.5", 2, 1, bbox=b1),
        tf_cell("4.5 6.5", 2, 2, bbox=b2),
    ]
    grid = [[None] * 3 for _ in range(3)]
    for c in cells:
        grid[c["start_row_offset_idx"]][c["start_col_offset_idx"]] = c
    tbl = {
        "prov": [
            {"page_no": 1, "bbox": {"l": 5, "t": 5, "r": 130, "b": 45, "coord_origin": "TOPLEFT"}}
        ],
        "data": {"table_cells": cells, "grid": grid, "num_rows": 3, "num_cols": 3},
    }
    return {"tables": [tbl], "pages": {"1": {"size": {"height": 200}}}}, page


def body(tbl: dict) -> list[list[str]]:
    return [
        [c["text"] for c in row]
        for row in tbl["data"]["grid"]
        if not any(c["column_header"] for c in row)
    ]


def test_config_holds_the_frozen_values() -> None:
    assert P.sources == ["eia", "govinfo_erp"]  # D-039 scope
    assert (P.trigger.gap_size_ratio, P.tokens.gap_size_ratio) == (0.25, 0.15)
    assert P.merged_cell_min_numbers == 2 and P.dense_band_line_divisor == 10


def test_merged_rows_fire_and_are_rebuilt_from_the_text_layer() -> None:
    doc, page = merged_doc()
    assert rows.merged_body_cells(doc["tables"][0], P) == 2
    log = rows.fix_document(doc, _Pdf(page), "eia", P)
    assert log[0]["status"] == "rebuilt"
    assert body(doc["tables"][0]) == [
        ["2020", "1.5", "2.5"],
        ["2021", "3.5", "4.5"],
        ["2022", "5.5", "6.5"],
    ]


def test_header_text_is_asserted_against_the_page() -> None:
    doc, page = merged_doc()
    rows.fix_document(doc, _Pdf(page), "eia", P)
    heads = {c["text"] for c in doc["tables"][0]["data"]["table_cells"] if c["column_header"]}
    assert {"Coal", "Gas"} <= heads
    # TableFormer's head disagrees with the page -> the page words win (logged)
    doc, page = merged_doc()
    doc["tables"][0]["data"]["table_cells"][1]["text"] = "Coke"
    log = rows.fix_document(doc, _Pdf(page), "eia", P)
    heads = {c["text"] for c in doc["tables"][0]["data"]["table_cells"] if c["column_header"]}
    assert "Coal" in heads and "Coke" not in heads
    assert any("header check" in n for n in log[0]["notes"])


def test_budget_cbo_pass_through_unchanged() -> None:
    doc, page = merged_doc()
    before = copy.deepcopy(doc)
    log = rows.fix_document(doc, _Pdf(page), "govinfo_budget", P)
    assert doc == before and log[0]["status"] == "out of scope (D-039)"


def test_unfired_table_is_untouched() -> None:
    doc, page = merged_doc()
    t = doc["tables"][0]["data"]
    b1, b2 = t["table_cells"][4]["bbox"], t["table_cells"][5]["bbox"]
    t["table_cells"] = t["table_cells"][:6] + [  # TableFormer got every row right
        tf_cell("2021", 2, 0),
        tf_cell("3.5", 2, 1, bbox=b1),
        tf_cell("4.5", 2, 2, bbox=b2),
        tf_cell("2022", 3, 0),
        tf_cell("5.5", 3, 1, bbox=b1),
        tf_cell("6.5", 3, 2, bbox=b2),
    ]
    t["grid"] = [t["table_cells"][i : i + 3] for i in range(0, 12, 3)]
    before = copy.deepcopy(doc)
    log = rows.fix_document(doc, _Pdf(page), "eia", P)
    assert doc == before and log[0]["status"] == "not fired"


def test_cell_text_rules() -> None:
    tok = lambda *ws: [{"text": w} for w in ws]  # noqa: E731
    assert rows.cell_text(tok("11", ",459")) == "11,459"  # split number rejoined
    assert rows.cell_text(tok("12", "34")) == "12 34"
    assert rows.flag_space("R1,358") == "R 1,358" and rows.flag_space("RF94") == "RF94"
    paren = [{"text": w} for w in ("(billion", "2017", "dollars)", "23,548")]
    assert rows.in_parenthetical(paren) == {0, 1, 2}
    assert rows.in_parenthetical([{"text": w} for w in ("(", "h", "8")]) == set()  # unclosed


def test_port_imports_nothing_from_scripts() -> None:
    src = Path(rows.__file__).read_text(encoding="utf-8")
    names = {
        a.name if isinstance(n, ast.Import) else (n.module or "")
        for n in ast.walk(ast.parse(src))
        if isinstance(n, ast.Import | ast.ImportFrom)
        for a in (n.names if isinstance(n, ast.Import) else [n])
    }
    assert not any(x.split(".")[0] in {"emit", "trigger", "oracle", "scripts"} for x in names)
