"""A1 diagnostics items 3 and 5 - instrumented re-parse of the pages holding the ten A1 tables.

Parses only the pages that hold A1's ten tables (both ERP pages, twelve table-pages in all) with the
corpus converter, ``ledger.ingest.parse.build_converter(cfg)``, one ``page_range=(p, p)`` call per
page, and records per TableFormer call - without editing the library:

* ``len(rs_seq)``, the generated tag count, ``max_steps``, and **cap hit**: the decoder
  (``tablemodel04_rs.py``) stops on ``<end>`` or after ``max_steps`` tags, and ``_get_html_tags``
  strips the last token either way, so a sequence whose last tag is not ``<end>`` hit the cap and
  lost a real tag;
* every ``MatchingPostProcessor`` drop WARNING and its DEBUG list of dropped pdf-cell ids,
  attributed to the exact call it fired inside (thread-local), not to a parse window;
* the raw material for item 4: predicted cell boxes before and after post-processing, and the word
  tokens TableFormer was given.

**Control:** each re-parsed table is compared with the saved table in ``data/parsed/`` (same
page, best bbox IoU). ``baseline`` must reproduce every one exactly, or page-limited parsing is
not a valid stand-in for the corpus parse. Re-parsed tables are spliced into a copy of the saved
unit JSON so the owner's A1 scripts score them with table indices unchanged.

Outputs, never over ``data/parsed``: ``data/parsed_a1diag/<config>/`` (spliced units, ``_pages/``,
``_capture/``) and ``reports/a1_diag/reparse_<config>.md``.

    uv run python scripts/a1_diag/reparse.py --config baseline
    uv run python scripts/a1_diag/reparse.py --config fast
    uv run python scripts/a1_diag/reparse.py --config wsw --wsw-factor 0.10
    uv run python scripts/a1_diag/reparse.py --config v2
"""

from __future__ import annotations

import argparse
import copy
import json
import logging
import re
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from ledger.config import load_config  # noqa: E402
from ledger.ingest.parse import build_converter  # noqa: E402

# A1's ten tables as (unit, saved table index); ERP counts both pages, so twelve table-pages.
AUDITED = (
    ("govinfo-ERP-2026-table4", 0),
    ("govinfo-ERP-2026-table4", 1),
    ("govinfo-ERP-2026-table22", 0),
    ("govinfo-ERP-2026-table22", 1),
    ("govinfo-BUDGET-2026-DOD", 446),
    ("govinfo-BUDGET-2026-DOD", 112),
    ("govinfo-BUDGET-2026-CROSSCUT", 45),
    ("eia-pdf-steo_full", 10),
    ("cbo-61959", 0),
    ("eia-pdf-sec3", 10),
    ("eia-pdf-sec11", 3),
    ("eia-pdf-sec4", 2),
)
PARSED = REPO / "data" / "parsed"
DOCLING_TABLE_SCALE = 2.0  # table_structure_model.py:96 - boxes and tokens reach TableFormer x2
DROP_RE = re.compile(r"(\d+) of (\d+) pdf cells matched neither .* the (\d+)x(\d+) grid")
IDS_RE = re.compile(r"Dropped pdf cell ids: \[(.*)\]")


# ---- instrumentation ---------------------------------------------------------------------------


@dataclass
class Call:
    page: int = 0
    tbl_box_page_img: list[float] = field(default_factory=list)  # docling's box, x2 page points
    page_img_size: tuple[float, float] = (0.0, 0.0)
    tokens: list[dict] = field(default_factory=list)
    max_steps: int = 0
    tag_seq_len: int = 0
    rs_seq_len: int = 0
    cap_hit: bool | None = None
    otsl_rows: int = 0
    otsl_cols: int = 0
    final_rows: int = 0
    final_cols: int = 0
    drops: list[dict] = field(default_factory=list)
    dropped_ids: list[str] = field(default_factory=list)
    pre_post: dict = field(default_factory=dict)
    post: dict = field(default_factory=dict)


STATE = threading.local()
CALLS: list[Call] = []
CURRENT_PAGE = {"page": 0}


class DropCapture(logging.Handler):
    """Attributes MatchingPostProcessor records to the TableFormer call running in this thread."""

    def emit(self, record: logging.LogRecord) -> None:
        # A handler must never raise into the library: an exception here aborts the conversion.
        try:
            call = getattr(STATE, "call", None)
            if call is None:
                return
            msg = record.getMessage()
            m = DROP_RE.search(msg)
            if m and record.levelno >= logging.WARNING:
                dropped, total, rows, cols = map(int, m.groups())
                call.drops.append(
                    {"dropped": dropped, "pdf_cells": total, "grid": f"{rows}x{cols}"}
                )
            m = IDS_RE.search(msg)
            if m:  # ids are logged as quoted strings: ['38', '41']
                call.dropped_ids += [x.strip(" '\"") for x in m.group(1).split(",") if x.strip()]
        except Exception:  # noqa: BLE001
            self.handleError(record)


def otsl_shape(rs_seq: list[str]) -> tuple[int, int]:
    rows = rs_seq.count("nl")
    cols = rs_seq.index("nl") if "nl" in rs_seq else len(rs_seq)
    return rows, cols


def _boxes(details: dict) -> dict:
    """The parts of matching_details item 4 needs, JSON-safe."""
    keep = {}
    for key in ("prediction_bboxes_page", "table_cells", "pdf_cells", "matches"):
        if key in details:
            keep[key] = copy.deepcopy(details[key])
    return keep


def install_instrumentation() -> None:
    from docling_ibm_models.tableformer.data_management import (
        matching_post_processor as mpp,
    )
    from docling_ibm_models.tableformer.data_management import tf_cell_matcher as tcm
    from docling_ibm_models.tableformer.data_management import tf_predictor as tfp

    # DEBUG so the "Dropped pdf cell ids" line (matching_post_processor.py, after :1238) is emitted;
    # the level is read from this module constant when each matcher builds its logger.
    mpp.LOG_LEVEL = logging.DEBUG
    logger = logging.getLogger("MatchingPostProcessor")
    logger.addHandler(DropCapture(level=logging.DEBUG))  # present first: no stdout handler added
    logger.propagate = False

    orig_multi = tfp.TFPredictor.multi_table_predict
    orig_predict = tfp.TFPredictor.predict
    orig_match = tcm.CellMatcher.match_cells

    def multi_table_predict(self, iocr_page, table_bboxes, do_matching=True, *a, **kw):
        calls = []
        for box in table_bboxes:
            call = Call(
                page=CURRENT_PAGE["page"],
                tbl_box_page_img=[float(v) for v in box],  # snapshot: the library rescales in place
                page_img_size=(float(iocr_page["width"]), float(iocr_page["height"])),
                tokens=copy.deepcopy(iocr_page.get("tokens", [])),
                max_steps=int(self._config["predict"]["max_steps"]),
            )
            calls.append(call)
        STATE.pending = list(calls)  # predict() pops from this copy; `calls` keeps all
        try:
            out = orig_multi(self, iocr_page, table_bboxes, do_matching, *a, **kw)
        finally:
            STATE.pending = []
        for call, res in zip(calls, out, strict=True):
            call.final_rows = int(res["predict_details"].get("num_rows", 0))
            call.final_cols = int(res["predict_details"].get("num_cols", 0))
            CALLS.append(call)
        return out

    def predict(self, iocr_page, table_bbox, table_image, scale_factor, *a, **kw):
        pending = getattr(STATE, "pending", [])
        call = pending.pop(0) if pending else Call(page=CURRENT_PAGE["page"])
        STATE.call = call
        try:
            tf_output, details = orig_predict(
                self, iocr_page, table_bbox, table_image, scale_factor, *a, **kw
            )
        finally:
            STATE.call = None
        pred = details.get("prediction", {})
        tag_seq = pred.get("tag_seq") or []
        rs_seq = pred.get("rs_seq") or []
        end_id = self._init_data["word_map"]["word_map_tag"]["<end>"]
        call.tag_seq_len = len(tag_seq)
        call.rs_seq_len = len(rs_seq)
        call.cap_hit = bool(tag_seq) and tag_seq[-1] != end_id
        call.otsl_rows, call.otsl_cols = otsl_shape(rs_seq)
        call.post = _boxes(details)
        return tf_output, details

    def match_cells(self, iocr_page, table_bbox, prediction):
        out = orig_match(self, iocr_page, table_bbox, prediction)
        call = getattr(STATE, "call", None)
        if call is not None:
            call.pre_post = _boxes(out)
        return out

    tfp.TFPredictor.multi_table_predict = multi_table_predict
    tfp.TFPredictor.predict = predict
    tcm.CellMatcher.match_cells = match_cells


# ---- converters --------------------------------------------------------------------------------


def make_converter(cfg, variant: str, wsw_factor: float | None):
    if variant == "baseline":
        return build_converter(cfg), {}
    if variant == "fast":
        parser = cfg.parser.model_copy(update={"table_mode": "fast"})
        return build_converter(cfg.model_copy(update={"parser": parser})), {"table_mode": "fast"}
    if variant == "wsw":
        if wsw_factor is None:
            raise SystemExit("--config wsw needs --wsw-factor")
        import docling.backend.docling_parse_backend as dpb

        orig = dpb._make_docling_parse_decode_config

        def patched(**kw):
            conf = orig(**kw)
            conf.word_space_width_factor_for_merge = wsw_factor
            return conf

        dpb._make_docling_parse_decode_config = patched  # before any document is opened
        return build_converter(cfg), {"word_space_width_factor_for_merge": wsw_factor}
    if variant == "v2":
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import TableStructureV2Options

        conv = build_converter(cfg)
        conv.format_to_options[
            InputFormat.PDF
        ].pipeline_options.table_structure_options = TableStructureV2Options()
        return conv, {"table_structure_options": "TableStructureV2Options()"}
    raise SystemExit(f"unknown config {variant!r}")


# ---- matching re-parsed tables to saved ones ---------------------------------------------


def to_topleft(bbox: dict, page_h: float) -> tuple[float, float, float, float]:
    left, top, right, bottom = bbox["l"], bbox["t"], bbox["r"], bbox["b"]
    if bbox.get("coord_origin", "BOTTOMLEFT") == "BOTTOMLEFT":
        return left, page_h - top, right, page_h - bottom
    return left, top, right, bottom


def iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def table_box(tbl: dict, doc: dict) -> tuple[int, tuple]:
    prov = tbl["prov"][0]
    page = prov["page_no"]
    page_h = doc["pages"][str(page)]["size"]["height"]
    return page, to_topleft(prov["bbox"], page_h)


def canon(data: dict) -> str:
    return json.dumps(data, sort_keys=True, ensure_ascii=False)


def first_difference(a: dict, b: dict) -> str:
    if (a.get("num_rows"), a.get("num_cols")) != (b.get("num_rows"), b.get("num_cols")):
        return (
            f"shape {a.get('num_rows')}x{a.get('num_cols')} -> "
            f"{b.get('num_rows')}x{b.get('num_cols')}"
        )
    ca, cb = a.get("table_cells", []), b.get("table_cells", [])
    if len(ca) != len(cb):
        return f"table_cells {len(ca)} -> {len(cb)}"
    for i, (x, y) in enumerate(zip(ca, cb, strict=True)):
        if canon(x) != canon(y):
            keys = sorted(k for k in set(x) | set(y) if x.get(k) != y.get(k))
            return f"cell {i}: {keys}"
    return "other fields"


# ---- main --------------------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", default="baseline", choices=("baseline", "fast", "wsw", "v2"))
    ap.add_argument("--wsw-factor", type=float, default=None)
    args = ap.parse_args()
    label = args.config if args.config != "wsw" else f"wsw{args.wsw_factor:g}"

    cfg = load_config()
    out_dir = REPO / "data" / "parsed_a1diag" / label
    (out_dir / "_pages").mkdir(parents=True, exist_ok=True)
    (out_dir / "_capture").mkdir(parents=True, exist_ok=True)
    report_path = REPO / "reports" / "a1_diag" / f"reparse_{label}.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)

    sources = {}
    for line in (REPO / "data" / "manifest.jsonl").read_text(encoding="utf-8").splitlines():
        rec = json.loads(line) if line.strip() else {}
        if rec.get("record") == "unit":
            sources[rec["unit_id"]] = rec["source"]

    saved = {u: json.loads((PARSED / f"{u}.json").read_text("utf-8")) for u, _ in AUDITED}
    audited = {(u, i) for u, i in AUDITED}
    pages: dict[str, list[int]] = {}
    for unit, ti in AUDITED:
        page = saved[unit]["tables"][ti]["prov"][0]["page_no"]
        pages.setdefault(unit, [])
        if page not in pages[unit]:
            pages[unit].append(page)

    install_instrumentation()
    converter, overrides = make_converter(cfg, args.config, args.wsw_factor)

    rows = []
    controls = []
    t0 = time.time()
    for unit, unit_pages in pages.items():
        pdf = REPO / cfg.paths.raw_dir / sources[unit] / f"{unit}.pdf"
        spliced = copy.deepcopy(saved[unit])
        for page in unit_pages:
            CURRENT_PAGE["page"] = page
            first_call = len(CALLS)
            started = time.time()
            result = converter.convert(str(pdf), page_range=(page, page))
            seconds = time.time() - started
            new = result.document.export_to_dict()
            (out_dir / "_pages" / f"{unit}_p{page}.json").write_text(
                json.dumps(new, ensure_ascii=False), encoding="utf-8"
            )
            page_calls = CALLS[first_call:]
            # saved tables on this page, by top-left box
            saved_on_page = [
                (i, table_box(t, saved[unit])[1])
                for i, t in enumerate(saved[unit]["tables"])
                if t["prov"][0]["page_no"] == page
            ]
            for nt in new.get("tables", []):
                npage, nbox = table_box(nt, new)
                best = max(saved_on_page, key=lambda s: iou(s[1], nbox), default=None)
                score = iou(best[1], nbox) if best else 0.0
                si = best[0] if best else None
                # the TableFormer call for this table: docling's box is the cluster box x2
                call = max(
                    page_calls,
                    key=lambda c: iou([v / DOCLING_TABLE_SCALE for v in c.tbl_box_page_img], nbox),
                    default=None,
                )
                identical = si is not None and canon(saved[unit]["tables"][si]["data"]) == canon(
                    nt["data"]
                )
                diff = (
                    ""
                    if identical or si is None
                    else first_difference(saved[unit]["tables"][si]["data"], nt["data"])
                )
                if si is not None:
                    spliced["tables"][si]["data"] = nt["data"]
                is_audited = (unit, si) in audited
                if is_audited:
                    controls.append(identical)
                if call is not None:
                    cap_path = out_dir / "_capture" / f"{unit}_p{npage}_t{si}.json"
                    cap_path.write_text(json.dumps(vars(call), default=str), encoding="utf-8")
                rows.append(
                    {
                        "unit": unit,
                        "page": npage,
                        "saved": f"#/tables/{si}" if si is not None else "-",
                        "iou": score,
                        "audited": is_audited,
                        "call": call,
                        "identical": identical,
                        "diff": diff,
                        "seconds": seconds,
                    }
                )
        (out_dir / f"{unit}.json").write_text(json.dumps(spliced, ensure_ascii=False), "utf-8")
    wall = time.time() - t0

    import docling
    import docling_core
    import docling_ibm_models

    def ver(mod) -> str:
        try:
            from importlib.metadata import version

            return version(mod.__name__.replace("_", "-"))
        except Exception:  # noqa: BLE001
            return "?"

    lines = [
        f"# A1 diagnostics - instrumented re-parse, config `{label}`",
        "",
        f"docling {ver(docling)} · docling-core {ver(docling_core)} · docling-ibm-models "
        f"{ver(docling_ibm_models)} · backend `{cfg.parser.pdf_backend}` · table_mode "
        f"`{overrides.get('table_mode', cfg.parser.table_mode)}` · "
        f"overrides {overrides or 'none'} · "
        f"{sum(len(p) for p in pages.values())} pages in {wall:.0f} s.",
        "",
        "Cap hit = the decoder stopped at `max_steps` without emitting `<end>` "
        "(`tablemodel04_rs.py`), so `_get_html_tags` also stripped a real final tag. "
        "OTSL shape = rows/cols read from `rs_seq` (`nl` count / first `nl`); final shape = after "
        "matching and post-processing.",
        "",
        "| unit | page | table | A1 | rs_seq | tags | max_steps | cap hit | OTSL shape | "
        "final shape | drop warnings | dropped ids | control |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        c: Call | None = r["call"]
        drops = (
            "; ".join(f"{d['dropped']} of {d['pdf_cells']} ({d['grid']})" for d in c.drops)
            if c
            else ""
        )
        control = "identical" if r["identical"] else f"**DIFFERENT** ({r['diff']})"
        lines.append(
            f"| `{r['unit']}` | {r['page']} | `{r['saved']}` | "
            f"{'**yes**' if r['audited'] else ''} | "
            + (
                f"{c.rs_seq_len} | {c.tag_seq_len} | {c.max_steps} | "
                f"{'**YES**' if c.cap_hit else 'no'} | {c.otsl_rows}x{c.otsl_cols} | "
                f"{c.final_rows}x{c.final_cols} | {drops or '0'} | "
                f"{len(c.dropped_ids) or ''} | "
                if c
                else "- | - | - | - | - | - | - | - | "
            )
            + f"{control} |"
        )
    n_ok = sum(controls)
    lines += [
        "",
        f"**Control (A1 tables): {n_ok} of {len(controls)} identical to `data/parsed/`.**"
        + (
            ""
            if args.config != "baseline"
            else (" PASS." if n_ok == len(controls) else " **FAIL - STOP.**")
        ),
    ]
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0 if (args.config != "baseline" or n_ok == len(controls)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
