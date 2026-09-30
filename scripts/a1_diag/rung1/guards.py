"""D-038 rung 1 - evaluation guards, flip matrix and baselines (A4; committed before any scoring).

``collect(parsed_dir)`` measures, on one parsed directory:

* **per-cell outcomes** on every admitted oracle cell - MER/ERP through
  ``oracle_score.score_table`` and STEO through ``steo_score.score_table`` (their ``detail``
  records; counts and denominators unchanged);
* **BUDGET/CBO tables** - per table: sha256 of the table dict (``json.dumps(sort_keys=True)``); the
  label-number pairs (report choice C4: (row-stub words, canon number) over cells holding exactly
  one number, the stub taken from the column-0 cell covering the row); word conservation (choice
  C5: page words inside the table bbox vs cell words, both normalised - NFKC, U+FFFD decimals to
  ".", leader-dot runs dropped, fused negatives split - conserved share = |cells & page| / |page|
  as multisets, excess = cell words beyond their page count).

``compare(base, new)`` evaluates, per family (never pooled):

* **flip matrix** - cells strict-correct at baseline and not after. Normalisation (owner, B5): the
  new text is re-read with R / E / RE flags stripped and fused negatives split at character level;
  a flip that disappears under that is **character-level** (flag / fused negative), reported
  apart; the rest are **value flips**, the number the <= 0.5 % line is judged on;
* **cells lost to repeated-label pairing** (STEO): a miss on a printed row whose label repeats in
  the table, where the value sits at the mapped column of another parsed row with that label.
  MER/ERP rows are keyed by period labels, unique per table: n/a.

    uv run --with pdfplumber python scripts/a1_diag/rung1/guards.py baseline
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import oracle as orc  # noqa: E402
import oracle_score as osc  # noqa: E402
import steo  # noqa: E402
import steo_score as ss  # noqa: E402
import trigger as tg  # noqa: E402

REPO = orc.REPO
OUT = REPO / "reports" / "a1_diag" / "rung1"
CACHE = REPO / "data" / "parsed_rung1" / "_cache" / "guards"
BASE = REPO / "data" / "parsed_rung1" / "_baseline"  # 7 MB: local; its sha256 is committed
TUNING = {("eia-pdf-sec3", 19), ("eia-pdf-sec4", 5)}
CODE = {"strict": "S", "wrong": "W", "row not found": "R", "column not found": "C"}


# ---- normalisation -------------------------------------------------------------------------------


LEADER_RUN = "[.…]{2,}"
# Correction made during Part B (build log 04:54Z): BUDGET's leader glyphs decode as runs of
# U+FFFD, and Docling prefixes them with U+0008. The A4 definition (LEADER_RUN, "v1") treated only
# "." / "..." runs as leaders, so every BUDGET stub compared its leader garbage, not its words. The
# corrected class ("v2") is applied identically to baseline and rung 1; both are reported.
LEADER_RUN_V2 = "[.…�]{2,}"
DEFINITION = "v2"


def norm_words(text: str, definition: str | None = None) -> list[str]:
    v2 = (definition or DEFINITION) == "v2"
    t = unicodedata.normalize("NFKC", text or "")
    t = re.sub(r"(?<=\d)�(?=\d)", ".", t)
    t = re.sub(r"(^|\s)(-?)�(?=\d)", r"\1\2.", t)
    if v2:
        t = t.replace("\x08", " ")
    out = []
    for w in t.split():
        for p in re.split(LEADER_RUN_V2 if v2 else LEADER_RUN, w):
            for q in re.split(r"(?<=\d)(?=[-−][\d.])", p):
                if q.strip():
                    out.append(q.strip())
    return out


def strip_flag(tok: str) -> str:
    return tg.FLAG.sub("", tok.strip())


def norm_value(text: str) -> list[str]:
    """Numbers in a cell text after the flip normalisation: flags stripped, fused negatives
    split at character level."""
    return [v for v in (orc.canon(strip_flag(w)) for w in norm_words(text)) if v is not None]


# ---- per-cell outcomes ---------------------------------------------------------------------------


def manifest() -> dict:
    out = {}
    for line in (REPO / "data" / "manifest.jsonl").read_text(encoding="utf-8").splitlines():
        rec = json.loads(line) if line.strip() else {}
        if rec.get("record") == "unit":
            out[rec["unit_id"]] = rec
    return out


def family_of(unit: str, page: int) -> str:
    if (unit, page) in TUNING:
        return "tuning"
    if unit == orc.STEO_UNIT:
        return "STEO"
    return "ERP" if "ERP" in unit else "MER held-out"


def cell_outcomes(parsed_dir: str) -> dict[str, dict]:
    """{table key: {family, codes, details}} for every oracle-covered table."""
    parsed = REPO / parsed_dir
    cells = [json.loads(x) for x in (orc.OUT / "cells.jsonl").open(encoding="utf-8")]
    groups: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for c in cells:
        if c["admitted"] and c.get("family") != "STEO":
            groups[(c["unit"], c["table_index"])].append(c)
    man = manifest()
    docs: dict[str, dict] = {}
    out = {}
    for (unit, ti), cs in sorted(groups.items()):
        doc = docs.setdefault(unit, json.loads((parsed / f"{unit}.json").read_text("utf-8")))
        pg = orc.read_page(unit, man[unit]["source"], ti, doc)
        detail: list = []
        osc.score_table(pg, doc["tables"][ti], cs, detail)
        out[f"{unit}|{ti}"] = {"family": family_of(unit, cs[0]["page"]), "details": detail}
    admitted, info = ss.load_oracle()
    sdoc = json.loads((parsed / f"{ss.UNIT}.json").read_text("utf-8"))
    for ti, d in sorted(info.items()):
        detail = []
        ss.score_table(sdoc["tables"][ti], d["page"], d["rows"], admitted.get(ti, []), detail)
        out[f"{ss.UNIT}|{ti}"] = {"family": "STEO", "details": detail}
    for v in out.values():
        v["codes"] = "".join(CODE[x["outcome"]] for x in v["details"])
    return out


# ---- BUDGET / CBO tables -------------------------------------------------------------------------


def label_number_pairs(tbl: dict) -> Counter:
    cells = tbl["data"].get("table_cells") or []
    label: dict[int, str] = {}
    for c in cells:
        if c.get("start_col_offset_idx") == 0:
            for r in range(c["start_row_offset_idx"], c["end_row_offset_idx"]):
                label[r] = " ".join(norm_words(c.get("text", "")))
    pairs: Counter = Counter()
    for c in cells:
        if c.get("start_col_offset_idx", 0) < 1 or c.get("column_header"):
            continue
        vals = norm_value(c.get("text", ""))
        if len(vals) == 1 and len([w for w in norm_words(c.get("text", "")) if tg.numeric(w)]) == 1:
            pairs[(label.get(c["start_row_offset_idx"], ""), vals[0])] += 1
    return pairs


def conservation(tbl: dict, page_tokens: list[list[dict]]) -> dict:
    page = Counter(w for ln in page_tokens for t in ln for w in norm_words(t["text"]))
    cellw = Counter(
        w for c in tbl["data"].get("table_cells") or [] for w in norm_words(c.get("text", ""))
    )
    conserved = sum((cellw & page).values())
    excess = sum((cellw - page).values())
    n = sum(page.values())
    return {
        "page_words": n,
        "conserved": conserved,
        "excess": excess,
        "share": round(conserved / n, 6) if n else None,
    }


def bc_tables(parsed_dir: str, tag: str) -> dict[str, dict]:
    import pdfplumber

    parsed = REPO / parsed_dir
    out = {}
    for path in sorted(parsed.glob("*.json")):
        unit = path.stem
        if path.name.endswith(".meta.json") or not ("BUDGET" in unit or unit.startswith("cbo-")):
            continue
        cache = CACHE / tag / f"{unit}.json"
        if cache.exists():
            out.update(json.loads(cache.read_text(encoding="utf-8")))
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        pdf = next((REPO / "data" / "raw").rglob(f"{unit}.pdf"))
        rows = {}
        with pdfplumber.open(pdf) as p:
            chars: dict[int, list] = {}
            for ti, tbl in enumerate(doc.get("tables", [])):
                rec = {
                    "family": "BUDGET" if "BUDGET" in unit else "CBO",
                    "sha256": hashlib.sha256(
                        json.dumps(tbl, sort_keys=True).encode("utf-8")
                    ).hexdigest(),
                }
                pairs = label_number_pairs(tbl)
                rec["pairs"] = sorted([list(k), v] for k, v in pairs.items())
                if tbl.get("prov"):
                    page, box = tg.table_box(doc, tbl)
                    if page not in chars:
                        chars[page] = p.pages[page - 1].chars
                    rec["conservation"] = conservation(tbl, tg.tokens_in(chars[page], box))
                rows[f"{unit}|{ti}"] = rec
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(rows), encoding="utf-8")
        out.update(rows)
    return out


# ---- flip matrix and pairing loss ----------------------------------------------------------------


def flips(base: dict, new: dict) -> dict[str, Counter]:
    per: dict[str, Counter] = defaultdict(Counter)
    for key, b in base.items():
        n = new[key]
        fam = b["family"]
        assert len(b["details"]) == len(n["details"]), key
        for bd, nd in zip(b["details"], n["details"], strict=True):
            per[fam]["cells"] += 1
            if bd["outcome"] != "strict":
                continue
            per[fam]["baseline_correct"] += 1
            if nd["outcome"] == "strict":
                continue
            if nd["outcome"] == "wrong" and bd["cell"]["value"] in norm_value(nd.get("text", "")):
                per[fam]["flip_character_level"] += 1
            else:
                per[fam]["flip_value"] += 1
    return per


def pairing_loss(parsed_dir: str, outcomes: dict) -> int:
    admitted, info = ss.load_oracle()
    sdoc = json.loads((REPO / parsed_dir / f"{ss.UNIT}.json").read_text("utf-8"))
    lost = 0
    for ti, d in info.items():
        grid = sdoc["tables"][ti]["data"].get("grid") or []
        printed = [steo.norm_label(r["label"]) for r in d["rows"]]
        reps = {lab for lab, k in Counter(printed).items() if k > 1}
        stub = [ss.stub_label(row[0].get("text", "")) if row else "" for row in grid]
        col_of: dict[str, int] = {}
        for x in outcomes[f"{ss.UNIT}|{ti}"]["details"]:
            if x["j"] is not None:
                col_of[x["cell"]["period"]] = x["j"]
        for x in outcomes[f"{ss.UNIT}|{ti}"]["details"]:
            c = x["cell"]
            lab = printed[c["row_index"]]
            j = col_of.get(c["period"])
            if x["outcome"] == "strict" or lab not in reps or j is None:
                continue
            if any(
                stub[r] == lab
                and r != x["r"]
                and j < len(grid[r])
                and orc.canon(grid[r][j].get("text", "").strip()) == c["value"]
                for r in range(len(grid))
            ):
                lost += 1
    return lost


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "baseline"
    if mode != "baseline":
        raise SystemExit("compare runs from rung1/evaluate.py at B5")
    outcomes = cell_outcomes("data/parsed")
    fam = defaultdict(Counter)
    for v in outcomes.values():
        fam[v["family"]].update(v["codes"])
    bc = bc_tables("data/parsed", "baseline")
    compact = {k: {"family": v["family"], "codes": v["codes"]} for k, v in outcomes.items()}
    body = {
        "cell_outcomes": compact,
        "family_totals": {k: dict(v) for k, v in fam.items()},
        "steo_pairing_loss": pairing_loss("data/parsed", outcomes),
        "bc_tables": bc,
    }
    text = json.dumps(body, sort_keys=True)
    BASE.mkdir(parents=True, exist_ok=True)
    (BASE / "baseline_guards.json").write_text(text, encoding="utf-8")
    print("sha256 baseline_guards.json", hashlib.sha256(text.encode()).hexdigest())
    for k, v in sorted(fam.items()):
        n = sum(v.values())
        print(f"{k}: strict {v['S']}/{n} = {v['S'] / n:.1%} (R {v['R']}, C {v['C']})")
    print("STEO pairing loss (baseline):", body["steo_pairing_loss"])
    print("BUDGET/CBO tables:", len(bc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
