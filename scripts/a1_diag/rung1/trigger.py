"""D-038 rung-1 trigger (FROZEN at the A1 dry-run commit; never modified after it).

Per table: fires iff the text layer's numeric-line count != TableFormer's rows, OR its band count
!= TableFormer's columns. Counted like-for-like (choice C1 in the rung-1 report):

* **Text layer** (pdfplumber characters inside the table's ``prov`` bbox; superscripts - chars
  smaller than 0.75x the median size - dropped). Characters are grouped into lines by vertical
  centre, and into tokens by x-gaps; a run of >= 2 leader dots separates tokens; a "-" / U+2212
  right after a digit starts a new token ("-0.02-0.02" is two). A token is numeric iff
  ``oracle.canon`` accepts it after an R / E / RE revision flag is stripped. A **numeric line**
  holds >= 1 numeric token that is not the line's leftmost token, and not only 4-digit years
  (a column-header year row). **Bands** = those tokens' right edges, clustered single-linkage
  within one median digit width.
* **TableFormer** (the saved grid): rows = grid rows with >= 1 numeric non-header cell in a
  column other than the stub (column 0); columns = columns >= 1 holding such a cell.

    uv run --with pdfplumber python scripts/a1_diag/rung1/trigger.py [--units U ...] [--check]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics as st
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import oracle as orc  # noqa: E402

REPO = orc.REPO
PARSED = REPO / "data" / "parsed"
CACHE = REPO / "data" / "parsed_rung1" / "_cache" / "trigger"
OUT = REPO / "reports" / "a1_diag" / "rung1"
FLAG = re.compile(r"^(RE|R|E)(?=[\d(.\-−�])|(?<=[\d)])(RE|R|E)$")
YEAR = re.compile(r"(19|20)\d\d")
TUNING = {("eia-pdf-sec3", 19), ("eia-pdf-sec4", 5)}


def numeric(text: str) -> bool:
    t = FLAG.sub("", text.strip())
    return bool(t) and orc.canon(t) is not None


def table_box(doc: dict, tbl: dict) -> tuple[int, tuple[float, float, float, float]]:
    prov = tbl["prov"][0]
    page = prov["page_no"]
    b = prov["bbox"]
    if b.get("coord_origin", "BOTTOMLEFT") == "BOTTOMLEFT":
        h = doc["pages"][str(page)]["size"]["height"]
        return page, (b["l"], h - b["t"], b["r"], h - b["b"])
    return page, (b["l"], b["t"], b["r"], b["b"])


def tokens_in(chars: list[dict], box: tuple[float, float, float, float]) -> list[list[dict]]:
    """Lines of tokens {text, x0, x1, top, bottom} inside ``box`` (top-left points)."""
    x0, top, x1, bottom = box
    inside = [
        c
        for c in chars
        if c["text"].strip()
        and x0 - 1 <= (c["x0"] + c["x1"]) / 2 <= x1 + 1
        and top - 1 <= (c["top"] + c["bottom"]) / 2 <= bottom + 1
    ]
    if not inside:
        return []
    med = st.median(c["size"] for c in inside)
    inside = [c for c in inside if c["size"] >= 0.75 * med]
    tol = 0.5 * st.median(c["bottom"] - c["top"] for c in inside)
    lines: list[list[dict]] = []
    for c in sorted(inside, key=lambda c: (c["top"] + c["bottom"]) / 2):
        cy = (c["top"] + c["bottom"]) / 2
        if lines and abs(cy - st.mean((d["top"] + d["bottom"]) / 2 for d in lines[-1])) <= tol:
            lines[-1].append(c)
        else:
            lines.append([c])
    return [char_tokens(sorted(ln, key=lambda c: c["x0"])) for ln in lines]


DOTS = ".…"
MINUS = "-−"


def char_tokens(ln: list[dict]) -> list[dict]:
    """One line's characters -> tokens, at character level: a break on an x-gap > 0.25 x size;
    a leader-dot run (>= 2 dots) is a break and is dropped; a minus right after a digit and
    before a digit or "." starts a new token ("-0.02-0.02" -> two)."""
    groups: list[list[dict]] = []
    for c in ln:
        if groups and c["x0"] - groups[-1][-1]["x1"] <= 0.25 * c["size"]:
            groups[-1].append(c)
        else:
            groups.append([c])
    toks: list[dict] = []
    for g in groups:
        texts = [c["text"] for c in g]
        cur: list[dict] = []
        for i, c in enumerate(g):
            ch = texts[i]
            in_run = ch in DOTS and (
                (i > 0 and texts[i - 1] in DOTS) or (i + 1 < len(g) and texts[i + 1] in DOTS)
            )
            if in_run:
                if cur:
                    toks.append(make_token(cur))
                cur = []
                continue
            if (
                ch in MINUS
                and cur
                and cur[-1]["text"].isdigit()
                and i + 1 < len(g)
                and (texts[i + 1].isdigit() or texts[i + 1] == ".")
            ):
                toks.append(make_token(cur))
                cur = []
            cur.append(c)
        if cur:
            toks.append(make_token(cur))
    return [t for t in toks if t["text"].strip()]


def make_token(cs: list[dict]) -> dict:
    return {
        "text": "".join(c["text"] for c in cs).strip(),
        "x0": min(c["x0"] for c in cs),
        "x1": max(c["x1"] for c in cs),
        "top": min(c["top"] for c in cs),
        "bottom": max(c["bottom"] for c in cs),
        "chars": cs,
    }


def text_counts(lines: list[list[dict]]) -> tuple[int, int, float]:
    num_lines, rights, widths = 0, [], []
    for ln in lines:
        vals = [t for t in ln[1:] if numeric(t["text"])]
        if not vals or all(YEAR.fullmatch(t["text"]) for t in vals):
            continue
        num_lines += 1
        for t in vals:
            rights.append(t["x1"])
            widths.append((t["x1"] - t["x0"]) / max(1, len(t["text"])))
    if not rights:
        return num_lines, 0, 0.0
    tol = st.median(widths)
    rights.sort()
    bands = 1 + sum(1 for a, b in zip(rights, rights[1:], strict=False) if b - a > tol)
    return num_lines, bands, tol


def tf_counts(tbl: dict) -> tuple[int, int]:
    grid = tbl["data"].get("grid") or []
    rows, cols = set(), set()
    for r, row in enumerate(grid):
        for j, c in enumerate(row):
            if j == 0 or c.get("column_header"):
                continue
            if any(numeric(w) for w in (c.get("text") or "").split()):
                rows.add(r)
                cols.add(j)
    return len(rows), len(cols)


def family(unit: str, ti: int, page: int, covered: set) -> str:
    if (
        (unit, page) in TUNING
        and unit in ("eia-pdf-sec3", "eia-pdf-sec4")
        and (unit, ti) in covered
    ):
        return "tuning"
    if unit in orc.MER_UNITS:
        return "MER held-out" if (unit, ti) in covered else "MER uncovered"
    if unit in orc.ERP_UNITS:
        return "ERP"
    if unit == orc.STEO_UNIT:
        return "STEO" if (unit, ti) in covered else "STEO uncovered"
    if "BUDGET" in unit:
        return "BUDGET"
    if unit.startswith("cbo-"):
        return "CBO"
    return "other"


def covered_tables() -> set:
    out = set()
    for line in (orc.OUT / "cells.jsonl").open(encoding="utf-8"):
        c = json.loads(line)
        if c["admitted"]:
            out.add((c["unit"], c["table_index"]))
    return out


def run_unit(unit: str, covered: set) -> list[dict]:
    cache = CACHE / f"{unit}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    import pdfplumber

    doc = json.loads((PARSED / f"{unit}.json").read_text(encoding="utf-8"))
    pdf = next((REPO / "data" / "raw").rglob(f"{unit}.pdf"))
    rows = []
    with pdfplumber.open(pdf) as p:
        chars_by_page: dict[int, list] = {}
        for ti, tbl in enumerate(doc.get("tables", [])):
            if not tbl.get("prov"):
                continue
            page, box = table_box(doc, tbl)
            if page not in chars_by_page:
                chars_by_page[page] = p.pages[page - 1].chars
            lines, bands, _ = text_counts(tokens_in(chars_by_page[page], box))
            tf_rows, tf_cols = tf_counts(tbl)
            rows.append(
                {
                    "unit": unit,
                    "table_index": ti,
                    "page": page,
                    "family": family(unit, ti, page, covered),
                    "numeric_lines": lines,
                    "tf_rows": tf_rows,
                    "bands": bands,
                    "tf_cols": tf_cols,
                    "fired": lines != tf_rows or bands != tf_cols,
                }
            )
    CACHE.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(rows), encoding="utf-8")
    return rows


def units() -> list[str]:
    return sorted(p.stem for p in PARSED.glob("*.json") if not p.name.endswith(".meta.json"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--units", nargs="*")
    ap.add_argument("--check", action="store_true", help="tuning tables only")
    ap.add_argument("--summarise", action="store_true")
    args = ap.parse_args()
    covered = covered_tables()
    if args.check:
        for unit in ("eia-pdf-sec3", "eia-pdf-sec4"):
            CACHE.joinpath(f"{unit}.json").unlink(missing_ok=True)
            for r in run_unit(unit, covered):
                if r["family"] == "tuning":
                    print(r)
            CACHE.joinpath(f"{unit}.json").unlink(missing_ok=True)
        return 0
    for unit in args.units or []:
        rows = run_unit(unit, covered)
        print(unit, len(rows), "tables,", sum(r["fired"] for r in rows), "fired")
    if args.summarise:
        rows = [r for u in units() for r in run_unit(u, covered)]
        OUT.mkdir(parents=True, exist_ok=True)
        body = json.dumps(rows, indent=0)
        (OUT / "trigger_dryrun.json").write_text(body, encoding="utf-8")
        fired = sorted([r["unit"], r["table_index"]] for r in rows if r["fired"])
        fired_body = json.dumps(fired)
        (OUT / "trigger_fired.json").write_text(fired_body, encoding="utf-8")
        fams: dict[str, list[int]] = {}
        for r in rows:
            f = fams.setdefault(r["family"], [0, 0])
            f[0] += 1
            f[1] += r["fired"]
        print("sha256 trigger_fired.json", hashlib.sha256(fired_body.encode()).hexdigest())
        for k, (n, f) in sorted(fams.items()):
            print(f"{k}: {f}/{n} fired")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
