"""A1 diagnostics item 4 - is TableFormer's *grid* wrong, its *boxes* wrong, or both (sec3, sec4)?

Reads item 3's capture (``data/parsed_a1diag/baseline/_capture/``): TableFormer's raw predicted
cells before post-processing (``row_id``, ``column_id``, box), the word tokens it was given, and
docling's own token -> cell matches (``matches``: pdf-cell id -> [(table_cell_id, iopdf)]). All are
in docling's table frame: top-left page coordinates x 2 (``table_structure_model.py:96``).

**Ground truth from the text layer.** Body lines = tokens clustered by vertical centre (a new line
when the centre moves by more than half the median token height), keeping lines with >= 3 numeric
tokens. Column bands = union of the x-extents of numeric tokens on body lines (right-aligned
figures of one column overlap; columns are separated by gaps). Cross-checked against pdfplumber's
own words in the same box.

**Decomposition.** Each band is mapped to the predicted column holding most of its tokens (by
docling's strongest match); each body line likewise to a predicted row.

* **Grid wrong** - two bands map to the same predicted column (the model has no column for one
  of them), or two lines map to the same predicted row, or the OTSL shape has fewer columns/rows
  than the text layer.
* **Boxes wrong** - the band or line has its own predicted column/row, but a token is matched to a
  cell in a different column/row: the box, not the grid, took it.

Every predicted cell that ends up holding >= 2 numeric tokens (a merge, same ``nums()`` as A1) is
attributed to exactly one cause: collapsed columns, collapsed rows, or box error.

Also reported for 5(b): whether any *word token* already holds two numbers before TableFormer sees
it (a backend merge - the only kind ``word_space_width_factor_for_merge`` can fix), and the
distribution of inter-column gaps and intra-number character gaps in em.

    uv run --with pdfplumber python scripts/a1_diag/grid_vs_boxes.py

Writes ``reports/a1_diag/grid_vs_boxes.md`` and one overlay PNG per table (gitignored).
"""

from __future__ import annotations

import json
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_owner_scripts import REPO, owner_nums  # noqa: E402

CAPTURE = REPO / "data" / "parsed_a1diag" / "baseline" / "_capture"
OUT = REPO / "reports" / "a1_diag"
SCALE = 2.0  # docling's table frame: page points x 2
TABLES = (
    ("eia-pdf-sec3", 19, 10, "eia"),
    ("eia-pdf-sec4", 5, 2, "eia"),
)
BAND_GAP_TOL = 1.0  # px in the x2 frame (0.5 pt): overlap-or-touch joins two extents into one band


def centre(b: dict | list) -> tuple[float, float]:
    if isinstance(b, dict):
        return (b["l"] + b["r"]) / 2, (b["t"] + b["b"]) / 2
    return (b[0] + b[2]) / 2, (b[1] + b[3]) / 2


def box(b: dict | list) -> tuple[float, float, float, float]:
    if isinstance(b, dict):
        return b["l"], b["t"], b["r"], b["b"]
    return b[0], b[1], b[2], b[3]


def cluster_lines(tokens: list[dict]) -> list[list[dict]]:
    heights = [box(t["bbox"])[3] - box(t["bbox"])[1] for t in tokens]
    tol = 0.5 * st.median(heights)
    lines: list[list[dict]] = []
    for tok in sorted(tokens, key=lambda t: centre(t["bbox"])[1]):
        cy = centre(tok["bbox"])[1]
        if lines and abs(cy - st.mean(centre(t["bbox"])[1] for t in lines[-1])) <= tol:
            lines[-1].append(tok)
        else:
            lines.append([tok])
    return lines


def bands_from(tokens: list[dict]) -> list[tuple[float, float]]:
    spans = sorted((box(t["bbox"])[0], box(t["bbox"])[2]) for t in tokens)
    bands: list[list[float]] = []
    for left, right in spans:
        if bands and left <= bands[-1][1] + BAND_GAP_TOL:
            bands[-1][1] = max(bands[-1][1], right)
        else:
            bands.append([left, right])
    return [(a, b) for a, b in bands]


def band_of(tok: dict, bands: list[tuple[float, float]]) -> int | None:
    cx = centre(tok["bbox"])[0]
    for i, (a, b) in enumerate(bands):
        if a - BAND_GAP_TOL <= cx <= b + BAND_GAP_TOL:
            return i
    return None


def majority(values: list) -> tuple[object, float]:
    if not values:
        return None, 0.0
    val, n = Counter(values).most_common(1)[0]
    return val, n / len(values)


def analyse(unit: str, page: int, ti: int, source: str, nums) -> tuple[list[str], dict]:
    cap = json.loads((CAPTURE / f"{unit}_p{page}_t{ti}.json").read_text(encoding="utf-8"))
    pre = cap["pre_post"]
    cells = {c["cell_id"]: c for c in pre["table_cells"]}
    matches = pre["matches"]  # str(pdf id) -> [{table_cell_id, iopdf}]
    tokens = [t for t in cap["tokens"] if t["text"].strip()]

    def is_num(t: dict) -> bool:
        return len(nums(t["text"])) >= 1 and not any(ch.isalpha() for ch in t["text"])

    backend_merges = [t["text"] for t in tokens if len(nums(t["text"])) > 1]
    lines = cluster_lines(tokens)
    body = [ln for ln in lines if sum(is_num(t) for t in ln) >= 3]
    body_num = [t for ln in body for t in ln if is_num(t) and len(nums(t["text"])) == 1]
    bands = bands_from(body_num)
    line_of = {t["id"]: i for i, ln in enumerate(body) for t in ln}

    def primary(tok: dict) -> dict | None:
        ms = matches.get(str(tok["id"])) or []
        if not ms:
            return None
        best = max(ms, key=lambda m: m["iopdf"])
        return cells.get(best["table_cell_id"])

    # band -> predicted column, line -> predicted row (majority of docling's own matches)
    band_tokens: dict[int, list[dict]] = defaultdict(list)
    for tok in body_num:
        b = band_of(tok, bands)
        if b is not None:
            band_tokens[b].append(tok)
    band_col, band_purity = {}, {}
    for b, toks in band_tokens.items():
        cols = [primary(t)["column_id"] for t in toks if primary(t)]
        band_col[b], band_purity[b] = majority(cols)
    line_row = {}
    for i, ln in enumerate(body):
        rows = [primary(t)["row_id"] for t in ln if is_num(t) and primary(t)]
        line_row[i], _ = majority(rows)

    col_users: dict[object, list[int]] = defaultdict(list)
    for b, c in band_col.items():
        col_users[c].append(b)
    row_users: dict[object, list[int]] = defaultdict(list)
    for i, r in line_row.items():
        row_users[r].append(i)
    collapsed_cols = {c: bs for c, bs in col_users.items() if c is not None and len(bs) > 1}
    collapsed_rows = {r: ls for r, ls in row_users.items() if r is not None and len(ls) > 1}

    # box errors: token matched to a column/row other than its own band's/line's, where that band
    # or line has a column/row of its own (not collapsed)
    unmatched = 0
    box_col_err = box_row_err = 0
    for tok in body_num:
        cell = primary(tok)
        if cell is None:
            unmatched += 1
            continue
        b = band_of(tok, bands)
        if b is not None and cell["column_id"] != band_col.get(b):
            box_col_err += 1
        i = line_of.get(tok["id"])
        if i is not None and cell["row_id"] != line_row.get(i):
            box_row_err += 1

    # attribute every predicted cell holding >= 2 numeric tokens (a merge) to one cause
    cell_tokens: dict[int, list[dict]] = defaultdict(list)
    for tok in body_num:
        cell = primary(tok)
        if cell is not None:
            cell_tokens[cell["cell_id"]].append(tok)
    causes: Counter = Counter()
    for toks in cell_tokens.values():
        if len(toks) < 2:
            continue
        tok_bands = {band_of(t, bands) for t in toks}
        tok_lines = {line_of.get(t["id"]) for t in toks}
        if len(tok_bands) > 1:
            same_pred_col = len({band_col.get(b) for b in tok_bands}) == 1
            causes["column collapse (grid)" if same_pred_col else "column straddle (box)"] += 1
        elif len(tok_lines) > 1:
            same_pred_row = len({line_row.get(i) for i in tok_lines}) == 1
            causes["row collapse (grid)" if same_pred_row else "row straddle (box)"] += 1
        else:
            causes["same band and line (split token)"] += 1

    # geometry: predicted boxes that overlap another predicted box
    boxes = [box(c["bbox"]) for c in pre["table_cells"]]
    overlaps = 0
    for i, a in enumerate(boxes):
        for b2 in boxes[i + 1 :]:
            ix = min(a[2], b2[2]) - max(a[0], b2[0])
            iy = min(a[3], b2[3]) - max(a[1], b2[1])
            if ix > 1 and iy > 1:
                overlaps += 1

    # pdfplumber cross-check, gap distributions (em and space widths) for 5(b)
    import pdfplumber

    pdf = REPO / "data" / "raw" / source / f"{unit}.pdf"
    tb = [v / SCALE for v in cap["tbl_box_page_img"]]
    with pdfplumber.open(pdf) as doc:
        full = doc.pages[page - 1]
        spaces = [c for c in full.chars if c["text"] == " "]
        pg = full.crop((tb[0], tb[1], tb[2], tb[3]))
        words = pg.extract_words(x_tolerance=1, keep_blank_chars=False)
        chars = pg.chars
    space_em = st.median((c["x1"] - c["x0"]) / c["size"] for c in spaces) if spaces else None
    intra = []  # gap between consecutive glyphs inside one numeric word, in em
    for w in words:
        if not nums(w["text"]) or any(ch.isalpha() for ch in w["text"]):
            continue
        glyphs = sorted(
            (
                c
                for c in chars
                if w["x0"] - 0.1 <= c["x0"]
                and c["x1"] <= w["x1"] + 0.1
                and abs(c["top"] - w["top"]) < 1.0
            ),
            key=lambda c: c["x0"],
        )
        for a, b in zip(glyphs, glyphs[1:], strict=False):
            intra.append((b["x0"] - a["x1"]) / max(a["size"], 1e-6))
    size = st.median(c["size"] for c in chars) if chars else 1.0
    inter = []  # gap between neighbouring numeric tokens in adjacent bands on one body line, in em
    for ln in body:
        row = sorted((t for t in ln if is_num(t)), key=lambda t: box(t["bbox"])[0])
        for a, b in zip(row, row[1:], strict=False):
            ba, bb = band_of(a, bands), band_of(b, bands)
            if ba is not None and bb is not None and bb == ba + 1:
                inter.append((box(b["bbox"])[0] - box(a["bbox"])[2]) / SCALE / size)
    sizes = Counter(round(c["size"], 1) for c in chars)

    # the stub adds a column only if its (alphabetic) labels sit outside every numeric band;
    # in the MER tables the stub holds the year labels, so it already is band 0
    stub_outside = [
        t
        for ln in body
        for t in ln
        if any(ch.isalpha() for ch in t["text"])
        and band_of(t, bands) is None
        and centre(t["bbox"])[0] < bands[0][0]
    ]
    visual_cols = len(bands) + (1 if stub_outside else 0)

    # rows: pixels per text line in TableFormer's input (every crop is resized to 448 x 448)
    pitch = st.median(
        centre(body[i + 1][0]["bbox"])[1] - centre(body[i][0]["bbox"])[1]
        for i in range(len(body) - 1)
    )
    crop_h = cap["tbl_box_page_img"][3] - cap["tbl_box_page_img"][1]
    px_per_line = 448 * pitch / crop_h

    grid_cols_wrong = bool(collapsed_cols) or cap["otsl_cols"] < visual_cols
    grid_rows_wrong = bool(collapsed_rows)
    n = max(len(body_num), 1)
    boxes_cols_wrong = box_col_err > 0.01 * n
    boxes_rows_wrong = box_row_err > 0.01 * n
    grid = [a for a, w in (("rows", grid_rows_wrong), ("columns", grid_cols_wrong)) if w]
    boxes = [a for a, w in (("rows", boxes_rows_wrong), ("columns", boxes_cols_wrong)) if w]
    verdict = (
        "both"
        if grid and boxes
        else "grid wrong"
        if grid
        else "boxes wrong"
        if boxes
        else "neither"
    )
    verdict += f" - grid wrong in {', '.join(grid) or 'nothing'}; boxes wrong in " + (
        ", ".join(boxes) or "nothing"
    )

    def q(vals: list[float], unit_div: float | None = None) -> str:
        if not vals:
            return "n/a"
        v = sorted(x / unit_div for x in vals) if unit_div else sorted(vals)
        return (
            f"n={len(v)} min {v[0]:.3f} · p5 {v[int(0.05 * (len(v) - 1))]:.3f} · "
            f"median {st.median(v):.3f} · max {v[-1]:.3f}"
        )

    threshold = f"{0.33 * space_em:.3f} em" if space_em else "n/a"
    lines_md = [
        f"## `{unit}` p{page} `#/tables/{ti}` - **{verdict}**",
        "",
        f"- Text layer: {len(tokens)} docling word tokens (pdfplumber: {len(words)} words in the "
        f"same box); **{len(body)} body lines** (pdfplumber agrees); **{len(bands)} numeric "
        f"column bands{' + 1 stub' if stub_outside else ' (band 0 is the year-label stub)'} = "
        f"{visual_cols} columns**.",
        f"- TableFormer: OTSL **{cap['otsl_rows']}x{cap['otsl_cols']}** "
        f"(cap hit: {cap['cap_hit']}), {len(pre['table_cells'])} predicted cells, "
        f"{overlaps} overlapping predicted-box pairs; final after post-processing "
        f"{cap['final_rows']}x{cap['final_cols']}.",
        f"- **Grid, columns:** {len(bands)} bands map onto "
        f"{len({c for c in band_col.values() if c is not None})} distinct predicted columns; "
        f"**{sum(len(v) - 1 for v in collapsed_cols.values())} band(s) without a column of "
        f"their own**; OTSL has {cap['otsl_cols']} columns for {visual_cols} visual.",
        f"- **Grid, rows:** {len(body)} body lines map onto "
        f"{len({r for r in line_row.values() if r is not None})} distinct predicted rows - "
        f"**{sum(len(v) - 1 for v in collapsed_rows.values())} line(s) share a predicted row "
        "with another line**.",
        f"- **Boxes:** of {len(body_num)} single-number body tokens, {box_col_err} matched into a "
        f"cell outside their band's column, **{box_row_err} outside their line's row**, "
        f"{unmatched} matched to no cell. Band purity (share of a band's tokens in its majority "
        f"column): min {min(band_purity.values()):.2f}, median "
        f"{st.median(band_purity.values()):.2f}.",
        f"- **Merges in the raw prediction** (predicted cells holding >= 2 numeric tokens), by "
        f"cause: {dict(causes) or 'none'}.",
        f"- **Resolution:** line pitch {pitch / SCALE:.2f} pt at glyph size {size:.1f} pt; the "
        f"table crop ({crop_h / SCALE:.0f} pt tall) is resized to 448 px, so each text line gets "
        f"**{px_per_line:.1f} px** of height in TableFormer's input.",
        f"- **Backend merges** (a single word token already holding >= 2 numbers): "
        f"**{len(backend_merges)}**{': ' + repr(backend_merges[:8]) if backend_merges else ''}.",
        f"- **5(b) geometry.** Space glyph {space_em:.3f} em (median of {len(spaces)} explicit "
        f"spaces on the page); default merge threshold 0.33 x space = {threshold}. "
        f"Inter-column gaps (em): {q(inter)}; in space widths: {q(inter, space_em)}. "
        f"Intra-number glyph gaps (em): {q(intra)}; in space widths: {q(intra, space_em)}. "
        f"Glyph sizes on the table: {dict(sizes.most_common(3))}.",
        "",
    ]
    stats = {
        "unit": unit,
        "verdict": verdict,
        "bands": len(bands),
        "visual_cols": visual_cols,
        "body_lines": len(body),
        "collapsed_bands": sum(len(v) - 1 for v in collapsed_cols.values()),
        "collapsed_lines": sum(len(v) - 1 for v in collapsed_rows.values()),
        "box_col_err": box_col_err,
        "box_row_err": box_row_err,
        "causes": dict(causes),
        "backend_merges": len(backend_merges),
        "space_em": space_em,
        "inter_min_em": min(inter) if inter else None,
        "intra_max_em": max(intra) if intra else None,
        "px_per_line": px_per_line,
    }
    overlay(unit, page, ti, cap, bands, cell_tokens, band_col, source)
    return lines_md, stats


def overlay(unit, page, ti, cap, bands, cell_tokens, band_col, src: str) -> None:
    """Page crop at the table frame's scale: predicted boxes (blue), merged cells (red), bands."""
    import pypdfium2 as pdfium
    from PIL import ImageDraw

    pdf = pdfium.PdfDocument(str(REPO / "data" / "raw" / src / f"{unit}.pdf"))
    img = pdf[page - 1].render(scale=SCALE).to_pil().convert("RGB")
    draw = ImageDraw.Draw(img, "RGBA")
    merged = {cid for cid, toks in cell_tokens.items() if len(toks) > 1}
    for c in cap["pre_post"]["table_cells"]:
        b = box(c["bbox"])
        fill = (255, 0, 0, 70) if c["cell_id"] in merged else None
        draw.rectangle(b, outline=(0, 90, 255, 200), fill=fill, width=1)
    t = cap["tbl_box_page_img"]
    for a, b in bands:
        draw.line([(a, t[1]), (a, t[3])], fill=(0, 170, 0, 160), width=1)
        draw.line([(b, t[1]), (b, t[3])], fill=(0, 170, 0, 160), width=1)
    img.crop([int(v) for v in t]).save(OUT / f"grid_vs_boxes_{unit}_p{page}.png")


def parse_tables(specs: list[str] | None) -> tuple:
    """``unit:page:table_index:source`` per table; default = item 4's sec3 and sec4."""
    if not specs:
        return TABLES
    out = []
    for spec in specs:
        unit, page, ti, source = spec.split(":")
        out.append((unit, int(page), int(ti), source))
    return tuple(out)


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tables", nargs="*", help="unit:page:table_index:source (item-3 capture)")
    ap.add_argument(
        "--out-name", default="grid_vs_boxes", help="report basename in reports/a1_diag"
    )
    args = ap.parse_args()
    tables = parse_tables(args.tables)
    nums = owner_nums((REPO / "reports" / "a1_scripts" / "pdf_recall.py").read_text("utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    md = [
        "# A1 diagnostics - grid vs boxes (item 4)",
        "",
        "Source: item 3's baseline capture (TableFormer's raw cells before post-processing, the "
        "word tokens, and docling's own token -> cell matches). Definitions in "
        "`scripts/a1_diag/grid_vs_boxes.py`. Overlays: blue = predicted cell boxes, red fill = "
        "predicted cells holding >= 2 numeric tokens, green = text-layer column bands.",
        "",
    ]
    all_stats = []
    for unit, page, ti, source in tables:
        lines, stats = analyse(unit, page, ti, source, nums)
        md += lines
        all_stats.append(stats)
    (OUT / f"{args.out_name}.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    (OUT / f"{args.out_name}.json").write_text(json.dumps(all_stats, indent=1), encoding="utf-8")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
