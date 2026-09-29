"""A1 step 0 item 4 (D-038 A2) - the half-crop test on sec3 p19, sec4 p5 and ERP-table4 p2.

Each table's crop is split into an upper and a lower half **at a text-line gap** (the gap between
consecutive text lines nearest the box's vertical middle, measured on the word tokens TableFormer
receives, never mid-line). TableFormer ``accurate`` runs on both halves **through the corpus
converter's table stage**: ``ledger.ingest.parse.build_converter(cfg)`` unchanged, with
``TFPredictor.multi_table_predict`` wrapped in-process for the target tables only (no library
edits). The two outputs are stitched before docling builds the TableItem:

* lower-half rows are offset by the upper half's row count;
* columns are aligned by clustering the two halves' column x-centres (a lower column joins the
  upper column whose centre lies within half the median column pitch, else it becomes its own);
* ``column_header`` is cleared on lower-half cells - that half has no header, so any header
  TableFormer predicts there is an artefact of the split (the count is reported).

Reported per table, before (the corpus parse and item 3's capture) and after:
* **merged rows** - parsed rows whose stub label holds more than one row key
  (``oracle_score.label_keys``), plus body cells holding >= 2 numbers (the census test);
* **text lines vs predicted rows** - body text lines (>= 3 numbers) against TableFormer's OTSL rows;
  **cap hits** per half;
* **strict / lenient** against the oracle (``oracle_score.score_table``, admitted cells).

Outputs go to ``--out-dir`` only (a scratch directory); the summary is also written to
``reports/a1_diag/half_crop.md``. ``data/parsed/`` is read, never written.

    uv run --with pdfplumber python scripts/a1_diag/half_crop.py --out-dir <scratch>
"""

from __future__ import annotations

import argparse
import copy
import json
import statistics as st
import sys
import threading
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import oracle as orc  # noqa: E402
import oracle_score as osc  # noqa: E402
from run_owner_scripts import owner_nums  # noqa: E402

TARGETS = (
    ("eia-pdf-sec3", 19, 10),
    ("eia-pdf-sec4", 5, 2),
    ("govinfo-ERP-2026-table4", 2, 1),
)
SCALE = 2.0  # docling's table frame: page points x 2 (table_structure_model.py:96)
STATE = threading.local()  # per-thread: the halves of the call in flight
CURRENT = {"page": 0}  # plain global: docling's table stage runs in a worker thread
TARGETS_TOPLEFT: dict[int, tuple[str, list[float]]] = {}  # page -> (unit, box in points)
LOG: dict[tuple[str, int], dict] = {}


# ---- geometry ----------------------------------------------------------------------------


def iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def split_y(tokens: list[dict], box: list[float]) -> tuple[float, int, int]:
    """y of the text-line gap nearest the box middle; also (lines above, lines below)."""
    inside = [
        t
        for t in tokens
        if box[0] <= (t["bbox"]["l"] + t["bbox"]["r"]) / 2 <= box[2]
        and box[1] <= (t["bbox"]["t"] + t["bbox"]["b"]) / 2 <= box[3]
    ]
    heights = [t["bbox"]["b"] - t["bbox"]["t"] for t in inside]
    tol = 0.5 * st.median(heights)
    lines: list[list[dict]] = []
    for t in sorted(inside, key=lambda t: (t["bbox"]["t"] + t["bbox"]["b"]) / 2):
        cy = (t["bbox"]["t"] + t["bbox"]["b"]) / 2
        if (
            lines
            and abs(cy - st.mean((x["bbox"]["t"] + x["bbox"]["b"]) / 2 for x in lines[-1])) <= tol
        ):
            lines[-1].append(t)
        else:
            lines.append([t])
    mid = (box[1] + box[3]) / 2
    best = None
    for i in range(len(lines) - 1):
        bottom = max(t["bbox"]["b"] for t in lines[i])
        top = min(t["bbox"]["t"] for t in lines[i + 1])
        if top <= bottom:
            continue  # no clean gap between these two lines
        y = (bottom + top) / 2
        if best is None or abs(y - mid) < abs(best[0] - mid):
            best = (y, i + 1, len(lines) - i - 1)
    if best is None:
        raise RuntimeError("no text-line gap in the table box")
    return best


def col_centres(cells: list[dict]) -> dict[int, float]:
    xs: dict[int, list[float]] = defaultdict(list)
    for c in cells:
        if c.get("col_span", 1) == 1 and c.get("bbox"):
            xs[c["start_col_offset_idx"]].append((c["bbox"]["l"] + c["bbox"]["r"]) / 2)
    return {k: st.mean(v) for k, v in xs.items()}


# ---- the stitch --------------------------------------------------------------------------


def stitch(upper: dict, lower: dict) -> tuple[dict, dict]:
    up, lo = upper["tf_responses"], lower["tf_responses"]
    nr_u = int(upper["predict_details"].get("num_rows", 0))
    cu, cl = col_centres(up), col_centres(lo)
    pitch = (
        st.median(b - a for a, b in zip(sorted(cu.values()), sorted(cu.values())[1:], strict=False))
        if len(cu) > 1
        else 50.0
    )
    # global columns: the upper half's, plus any lower column with no upper column near it
    centres = sorted(cu.values())
    lower_map: dict[int, float] = {}
    for k, x in sorted(cl.items()):
        near = min(centres, key=lambda c: abs(c - x), default=None)
        if near is not None and abs(near - x) <= 0.5 * pitch:
            lower_map[k] = near
        else:
            centres.append(x)
            centres.sort()
            lower_map[k] = x
    index_of = {c: i for i, c in enumerate(centres)}
    upper_map = {k: index_of[x] for k, x in cu.items()}
    lower_idx = {k: index_of[x] for k, x in lower_map.items()}

    def remap(cells, cmap, row_off, clear_header):
        out, cleared = [], 0
        for c in cells:
            c = copy.deepcopy(c)
            s, e = c["start_col_offset_idx"], c["end_col_offset_idx"]
            ns = cmap.get(s, s)
            ne = cmap.get(e - 1, e - 1) + 1
            c["start_col_offset_idx"], c["end_col_offset_idx"] = ns, max(ne, ns + 1)
            c["col_span"] = c["end_col_offset_idx"] - ns
            c["start_row_offset_idx"] += row_off
            c["end_row_offset_idx"] += row_off
            if clear_header and c.get("column_header"):
                c["column_header"] = False
                cleared += 1
            out.append(c)
        return out, cleared

    new_up, _ = remap(up, upper_map, 0, False)
    new_lo, cleared = remap(lo, lower_idx, nr_u, True)
    details = copy.deepcopy(upper["predict_details"])
    details["num_rows"] = nr_u + int(lower["predict_details"].get("num_rows", 0))
    details["num_cols"] = len(centres)
    rs_u = upper["predict_details"].get("prediction", {}).get("rs_seq", [])
    rs_l = lower["predict_details"].get("prediction", {}).get("rs_seq", [])
    details.setdefault("prediction", {})["rs_seq"] = list(rs_u) + list(rs_l)
    info = {
        "upper_cols": len(cu),
        "lower_cols": len(cl),
        "stitched_cols": len(centres),
        "lower_headers_cleared": cleared,
    }
    return {"tf_responses": new_up + new_lo, "predict_details": details}, info


def install() -> None:
    """Wrap multi_table_predict for the page/box in ``TARGETS_TOPLEFT`` (target tables only)."""
    from docling_ibm_models.tableformer.data_management import tf_predictor as tfp

    orig = tfp.TFPredictor.multi_table_predict
    orig_predict = tfp.TFPredictor.predict

    def predict(self, *a, **kw):  # record rs_seq length and cap hit per half
        out = orig_predict(self, *a, **kw)
        pred = out[1].get("prediction", {})
        tags = pred.get("tag_seq") or []
        end = self._init_data["word_map"]["word_map_tag"]["<end>"]
        getattr(STATE, "halves", []).append(
            {
                "rs_seq": len(pred.get("rs_seq") or []),
                "cap_hit": bool(tags) and tags[-1] != end,
                "otsl_rows": (pred.get("rs_seq") or []).count("nl"),
            }
        )
        return out

    def multi(self, iocr_page, table_bboxes, do_matching=True, *a, **kw):
        page = CURRENT["page"]
        target = TARGETS_TOPLEFT.get(page)
        if not target or len(table_bboxes) != 1:
            return orig(self, iocr_page, table_bboxes, do_matching, *a, **kw)
        unit, box_pt = target
        box = [float(v) for v in table_bboxes[0]]
        if iou([v / SCALE for v in box], box_pt) < 0.5:
            return orig(self, iocr_page, table_bboxes, do_matching, *a, **kw)
        y, above, below = split_y(iocr_page["tokens"], box)
        upper_box = [box[0], box[1], box[2], y]
        lower_box = [box[0], y, box[2], box[3]]
        STATE.halves = []

        def own_tokens(half: list[float]) -> dict:
            # each half gets ONLY its own words: docling passes the whole table's tokens, and a
            # half's matcher would otherwise pile the other half's words onto its boundary row
            toks = [
                t
                for t in iocr_page["tokens"]
                if half[1] <= (t["bbox"]["t"] + t["bbox"]["b"]) / 2 < half[3]
            ]
            return {**iocr_page, "tokens": toks}

        outs = [
            orig(self, own_tokens(upper_box), [upper_box], do_matching, *a, **kw)[0],
            orig(self, own_tokens(lower_box), [lower_box], do_matching, *a, **kw)[0],
        ]
        stitched, info = stitch(outs[0], outs[1])
        LOG[(unit, page)] = {
            "split_y_pt": y / SCALE,
            "lines_above": above,
            "lines_below": below,
            "halves": list(STATE.halves),
            **info,
            "rows_upper": outs[0]["predict_details"].get("num_rows"),
            "rows_lower": outs[1]["predict_details"].get("num_rows"),
        }
        return [stitched]

    tfp.TFPredictor.predict = predict
    tfp.TFPredictor.multi_table_predict = multi


# ---- measures ----------------------------------------------------------------------------


def merged_rows(tbl: dict) -> int:
    state: dict = {}
    n = 0
    for row in tbl["data"].get("grid") or []:
        if row and len(osc.label_keys(row[0].get("text", ""), state)) > 1:
            n += 1
    return n


def merged_cells(tbl: dict, nums) -> int:
    return sum(
        1
        for c in tbl["data"].get("table_cells", [])
        if not c.get("column_header")
        and not c.get("row_header")
        and len(nums(c.get("text", ""))) > 1
    )


def main() -> int:
    from ledger.config import load_config
    from ledger.ingest.parse import build_converter

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out-dir", required=True, help="scratch directory for the re-parses")
    args = ap.parse_args()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    cfg = load_config()
    nums = owner_nums((REPO / "reports" / "a1_scripts" / "pdf_recall.py").read_text("utf-8"))
    manifest = {}
    for line in (REPO / "data" / "manifest.jsonl").read_text(encoding="utf-8").splitlines():
        rec = json.loads(line) if line.strip() else {}
        if rec.get("record") == "unit":
            manifest[rec["unit_id"]] = rec
    cells = [json.loads(x) for x in (orc.OUT / "cells.jsonl").open(encoding="utf-8")]

    install()
    conv = build_converter(cfg)
    saved = {
        u: json.loads((REPO / "data" / "parsed" / f"{u}.json").read_text("utf-8"))
        for u, _, _ in TARGETS
    }
    rows = []
    for unit, page, ti in TARGETS:
        tbl = saved[unit]["tables"][ti]
        h = saved[unit]["pages"][str(page)]["size"]["height"]
        bb = tbl["prov"][0]["bbox"]
        box_pt = [bb["l"], h - bb["t"], bb["r"], h - bb["b"]]
        TARGETS_TOPLEFT.clear()
        TARGETS_TOPLEFT[page] = (unit, box_pt)
        CURRENT["page"] = page
        res = conv.convert(
            str(REPO / "data" / "raw" / manifest[unit]["source"] / f"{unit}.pdf"),
            page_range=(page, page),
        )
        new = res.document.export_to_dict()
        (out / f"{unit}_p{page}_halfcrop.json").write_text(json.dumps(new), encoding="utf-8")
        # splice the half-crop table into a copy of the saved unit (same index as the corpus)
        best = max(
            new.get("tables", []),
            key=lambda t: iou(
                [
                    t["prov"][0]["bbox"]["l"],
                    h - t["prov"][0]["bbox"]["t"],
                    t["prov"][0]["bbox"]["r"],
                    h - t["prov"][0]["bbox"]["b"],
                ],
                box_pt,
            ),
        )
        spliced = copy.deepcopy(saved[unit])
        spliced["tables"][ti]["data"] = best["data"]
        (out / f"{unit}.json").write_text(json.dumps(spliced), encoding="utf-8")

        pg = orc.read_page(unit, manifest[unit]["source"], ti, saved[unit])
        cs = [c for c in cells if c["unit"] == unit and c["table_index"] == ti and c["admitted"]]
        before = osc.score_table(pg, tbl, cs)
        after = osc.score_table(pg, spliced["tables"][ti], cs)
        cap = json.loads(
            (
                REPO
                / "data"
                / "parsed_a1diag"
                / "baseline"
                / "_capture"
                / f"{unit}_p{page}_t{ti}.json"
            ).read_text("utf-8")
        )
        body_lines = len(pg.lines)
        log = LOG.get((unit, page), {})
        rows.append(
            {
                "unit": unit,
                "page": page,
                "table": f"#/tables/{ti}",
                "body_lines": body_lines,
                "before": {
                    "otsl_rows": cap["otsl_rows"],
                    "cap_hit": cap["cap_hit"],
                    "final": f"{tbl['data']['num_rows']}x{tbl['data']['num_cols']}",
                    "merged_rows": merged_rows(tbl),
                    "merged_cells": merged_cells(tbl, nums),
                    "strict": before["strict"],
                    "lenient": before["lenient"],
                    "cells": before["cells"],
                },
                "after": {
                    "otsl_rows": sum(x["otsl_rows"] for x in log.get("halves", [])),
                    "cap_hit": [x["cap_hit"] for x in log.get("halves", [])],
                    "final": f"{best['data']['num_rows']}x{best['data']['num_cols']}",
                    "merged_rows": merged_rows(best),
                    "merged_cells": merged_cells(best, nums),
                    "strict": after["strict"],
                    "lenient": after["lenient"],
                    "cells": after["cells"],
                },
                "split": log,
            }
        )
    (out / "half_crop.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    report(rows)
    return 0


def report(rows: list[dict]) -> None:
    def pct(a, b):
        return f"{a / b:.1%}" if b else "n/a"

    lines = [
        "# A1 step 0, item 4 - half-crop test (D-038 A2)",
        "",
        "Split at the text-line gap nearest the middle; TableFormer accurate on each half through "
        "the corpus converter's table stage; stitched on the shared columns. Definitions in "
        "`scripts/a1_diag/half_crop.py`.",
        "",
        "| table | text lines | OTSL rows before -> after (upper+lower) | "
        "cap hit before -> after | "
        "final shape before -> after | merged rows | merged body cells | strict | lenient | "
        "split / columns |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        b, a, s = r["before"], r["after"], r["split"]
        halves = s.get("halves", [])
        lines.append(
            f"| `{r['unit']}` p{r['page']} | {r['body_lines']} | "
            f"{b['otsl_rows']} -> {a['otsl_rows']} "
            f"({' + '.join(str(x['otsl_rows']) for x in halves)}) | {b['cap_hit']} -> "
            f"{[x['cap_hit'] for x in halves]} | {b['final']} -> {a['final']} | "
            f"{b['merged_rows']} -> {a['merged_rows']} | "
            f"{b['merged_cells']} -> {a['merged_cells']} | "
            f"{pct(b['strict'], b['cells'])} -> **{pct(a['strict'], a['cells'])}** | "
            f"{pct(b['lenient'], b['cells'])} -> {pct(a['lenient'], a['cells'])} | "
            f"lines {s.get('lines_above')}/{s.get('lines_below')}; cols {s.get('upper_cols')}/"
            f"{s.get('lower_cols')} -> {s.get('stitched_cols')}; lower headers cleared "
            f"{s.get('lower_headers_cleared')} |"
        )
    path = REPO / "reports" / "a1_diag" / "half_crop.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    raise SystemExit(main())
