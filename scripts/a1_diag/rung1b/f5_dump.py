"""D-039 status 2026-09-30, ruling (1)-(2): diagnose the 23 anomalous not-on-the-line cells on the
BURNED pilot MER tables (<= 30 min). Reads ``F5_sizing.json``; does not change admission.

The 23 = not-on-the-line cells whose band text is not a single numeric token once a leading /
trailing R / E / RE flag is stripped, attached or separated by whitespace (the census rule), minus
the NA / (s) placeholders. For each: every pdfplumber char on the row's line (text, fontname, size,
top, bottom, x0, x1), the chars inside the cell's band on the two lines above and below, and a
300-dpi crop of the band x two lines either side (``reports/a1_diag/rung1b/f5_crops/``).

Automatic pre-class into the four committed outcomes (+ the split-token rule), confirmed on the
crops by eye: footnote-fused (a letter fused to the value's digits), split-token (the band's tokens
joined == value -> checker geometry; != value -> numeric-but-different), digit-on-other-line (the
value in the band on an adjacent line -> checker geometry), value-on-line-but-band-empty (the
value's digits on the row's line outside the band), else no-digit-at-position (decode defect).

    uv run --with pdfplumber python scripts/a1_diag/rung1b/f5_dump.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import f5_sizing as f5  # noqa: E402
import oracle as orc  # noqa: E402

REPO = orc.REPO
OUT = REPO / "reports" / "a1_diag" / "rung1b"
CROPS = OUT / "f5_crops"
FLAGS = {"R", "E", "RE"}
FIELDS = ("text", "fontname", "size", "top", "bottom", "x0", "x1")


def tolerant_tokens(text: str) -> list[str]:
    toks = text.split()
    out, i = [], 0
    while i < len(toks):
        if toks[i] in FLAGS and i + 1 < len(toks):
            out.append(toks[i + 1])
            i += 2
        else:
            out.append(f5.FLAG.sub("", toks[i]))
            i += 1
    return out


def anomalous(cells: list[dict]) -> list[dict]:
    out = []
    for c in cells:
        if c["outcome"] != "not on the line":
            continue
        p = c["page_prints_in_band"]
        toks = [] if p == "(nothing in the band)" else tolerant_tokens(p)
        if len(toks) == 1 and orc.canon(toks[0]) is not None:
            continue  # numeric-but-different
        if len(toks) == 1 and (toks[0] in orc.PLACEHOLDERS or toks[0] == "NA"):
            continue  # placeholder: page != export
        out.append(c)
    return out


def digits(v: str) -> str:
    return re.sub(r"\D", "", v)


def preclass(c: dict, line_chars: list[dict], band: tuple, near: list[list[dict]]) -> str:
    in_band = [
        ch for ch in line_chars if band[0] - 0.5 <= (ch["x0"] + ch["x1"]) / 2 <= band[1] + 0.5
    ]
    band_text = "".join(ch["text"] for ch in in_band).strip()
    toks = (
        c["page_prints_in_band"].split()
        if c["page_prints_in_band"] != "(nothing in the band)"
        else []
    )
    if len(toks) >= 2 and all(orc.canon(t) is not None for t in toks):
        joined = orc.canon("".join(toks))
        return (
            "split-token, joined == value"
            if joined == c["value_canon"]
            else ("split-token, joined != value (numeric-but-different)")
        )
    if (
        in_band
        and re.search(r"[A-Za-z]", band_text)
        and digits(c["expected"])
        and digits(c["expected"]) in digits(band_text)
        and not re.search(r"[^\d.,\-A-Za-z ()]", band_text)
    ):
        letters = re.sub(r"[\d.,\- ]", "", band_text)
        if letters and letters not in ("R", "E", "RE"):
            return "footnote-fused"
    for other in near:
        ob = "".join(
            ch["text"]
            for ch in other
            if band[0] - 0.5 <= (ch["x0"] + ch["x1"]) / 2 <= band[1] + 0.5
        )
        if orc.canon(ob.strip()) == c["value_canon"]:
            return "digit-on-other-line"
    if not in_band:
        whole = "".join(ch["text"] for ch in line_chars)
        if digits(c["expected"]) and re.search(
            rf"(?<!\d){re.escape(digits(c['expected']))}(?!\d)", whole
        ):
            return "value-on-line-but-band-empty"
    return "no-digit-at-position"


# Confirmed on the crops by eye (18:20-18:22Z); key = dump row number. Class names are the four
# committed outcomes plus the split-token rule; "outside" = fits none of them.
CONFIRMED = {
    1: ("no-digit-at-position", "prints 17.8 (= expected); the 8 decodes as '!;!'"),
    2: ("footnote-fused", "prints superscript b + 17.1 (= expected)"),
    3: ("no-digit-at-position", "prints superscript R + 8 (= expected); the 8 decodes as 'a'"),
    4: ("digit-on-other-line", "bold annual row; the band digits are grouped onto another line"),
    5: ("digit-on-other-line", "bold annual row; the band digits are grouped onto another line"),
    6: ("no-digit-at-position", "prints superscript E + 90 (!= expected 105); 90 decodes as 'gQ'"),
    7: (
        "no-digit-at-position",
        "prints superscript E + 130 (!= expected 103); the 0 decodes as 'Q'",
    ),
    8: (
        "digit-on-other-line",
        "prints 1 (= expected) on the row; the glyph grouped onto another line",
    ),
    9: ("no-digit-at-position", "prints 1,070 (= expected); the 0 decodes as 'Q'"),
    **{
        n: (
            "digit-on-other-line",
            "prints 1 (= expected) on the row; the glyph grouped onto another line",
        )
        for n in range(10, 20)
    },
    20: (
        "outside",
        "prints superscript RF + 4 (!= expected 14): flag 'RF' is not in the R/E/RE strip",
    ),
    21: ("split-token, joined != value (numeric-but-different)", "prints 213 (!= expected 225)"),
    22: ("footnote-fused", "prints superscript d + 5 (= expected)"),
    23: ("split-token, joined == value", "prints 2,017 (= expected); x-gap split '2,01 7'"),
}


def main() -> int:
    import pdfplumber

    d = json.loads((OUT / "F5_sizing.json").read_text(encoding="utf-8"))
    cells = anomalous(d["cells"])
    assert len(cells) == 23, len(cells)
    admitted = {
        (c["unit"], c["table_index"], c["row"], c["band"]): c
        for c in map(json.loads, (orc.OUT / "cells.jsonl").open(encoding="utf-8"))
        if c["admitted"] and c["unit"] in orc.MER_UNITS
    }
    CROPS.mkdir(parents=True, exist_ok=True)
    rows, dump = [], []
    cache: dict = {}
    for n, c in enumerate(cells, 1):
        key = next(
            k
            for k in admitted
            if k[0] == c["unit"]
            and k[2] == c["row"]
            and k[3] == c["band"]
            and admitted[k]["table_id"] == c["table"]
        )
        unit, ti = key[0], key[1]
        c["value_canon"] = admitted[key]["value"]
        rl = cache.setdefault((unit, ti), f5.row_lines(unit, ti))
        ln = rl["by_key"][c["row"]]
        idx = rl["lines"].index(ln)
        y0, y1 = min(t["top"] for t in ln), max(t["bottom"] for t in ln)
        lh = y1 - y0
        box = rl["box"]
        on_line = [
            ch
            for ch in rl["chars"]
            if box[0] - 1 <= (ch["x0"] + ch["x1"]) / 2 <= box[2] + 1
            and y0 - 0.25 * lh <= (ch["top"] + ch["bottom"]) / 2 <= y1 + 0.25 * lh
        ]
        near = []
        for j in (idx - 2, idx - 1, idx + 1, idx + 2):
            if 0 <= j < len(rl["lines"]):
                t0 = min(t["top"] for t in rl["lines"][j])
                t1 = max(t["bottom"] for t in rl["lines"][j])
                near.append(
                    [
                        ch
                        for ch in rl["chars"]
                        if t0 - 0.5 <= (ch["top"] + ch["bottom"]) / 2 <= t1 + 0.5
                        and box[0] - 1 <= (ch["x0"] + ch["x1"]) / 2 <= box[2] + 1
                    ]
                )
        band = rl["bands"][c["band"]]
        cls = preclass(c, on_line, band, near)
        name = f"{n:02d}_{c['table']}_{c['row'].replace(':', '-')}.png"
        with pdfplumber.open(REPO / "data" / "raw" / "eia" / f"{unit}.pdf") as pdf:
            page = pdf.pages[rl["page_no"] - 1]
            crop = (
                max(0, band[0] - 60),
                max(0, y0 - 2.5 * lh),
                min(page.width, band[1] + 30),
                min(page.height, y1 + 2.5 * lh),
            )
            page.crop(crop).to_image(resolution=300).save(CROPS / name)
        band_chars = [
            ch for ch in on_line if band[0] - 0.5 <= (ch["x0"] + ch["x1"]) / 2 <= band[1] + 0.5
        ]
        rows.append(
            {
                "n": n,
                "table": c["table"],
                "page": c["page"],
                "row": c["row"],
                "series": c["period"],
                "expected": c["expected"],
                "band_prints": c["page_prints_in_band"],
                "band_chars": " ".join(
                    f"{ch['text']}[{ch['fontname'].split('+')[-1]},{ch['size']:.1f}]"
                    for ch in band_chars
                )
                or "(none)",
                "preclass": cls,
                "class": CONFIRMED[n][0],
                "page_shows": CONFIRMED[n][1],
                "crop": f"reports/a1_diag/rung1b/f5_crops/{name}",
            }
        )
        dump.append(
            {
                **rows[-1],
                "line_chars": [{k: ch[k] for k in FIELDS} for ch in on_line],
                "near_band_chars": [
                    [
                        {k: ch[k] for k in FIELDS}
                        for ch in o
                        if band[0] - 0.5 <= (ch["x0"] + ch["x1"]) / 2 <= band[1] + 0.5
                    ]
                    for o in near
                ],
            }
        )
    (OUT / "F5_dump.json").write_text(json.dumps(dump, indent=0, default=float), encoding="utf-8")
    md = [
        "# D-039 clause (b): the 23 anomalous cells, diagnosed (burned MER tables)",
        "",
        "Chars per cell in `F5_dump.json`; crops in `f5_crops/`. `preclass` = the automatic "
        "reading "
        "of the char dump; `class` = confirmed on the crop by eye (the committed outcomes).",
        "",
        "| # | table | page | row | expected | band text | band chars [font,size] | preclass | "
        "**class** | the page shows | crop |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        md.append(
            f"| {r['n']} | {r['table']} | {r['page']} | {r['row']} | {r['expected']} | "
            f"`{r['band_prints']}` | {r['band_chars'][:70]} | {r['preclass']} | **{r['class']}** | "
            f"{r['page_shows']} | `{r['crop'].rsplit('/', 1)[-1]}` |"
        )
    from collections import Counter

    md += [
        "",
        "Classes: " + ", ".join(f"{k} {v}" for k, v in Counter(r["class"] for r in rows).items()),
    ]
    (OUT / "F5_dump.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    for r in rows:
        print(
            r["n"],
            r["table"],
            r["row"],
            r["expected"],
            repr(r["band_prints"]),
            "|",
            r["band_chars"][:90],
            "|",
            r["preclass"],
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
