"""Run the owner's A1 scoring scripts (``reports/a1_scripts/``) here, unchanged except for paths.

The scripts were written chat-side and hard-code ``U="/mnt/user-data/uploads/LEDGER/"``. This
runner copies each one into ``reports/a1_diag/repro/<label>/``, replaces only that root line (and,
for a diagnostic parse, the ``data/parsed/`` prefix), prints the diff so the change is visible, and
runs the copy from that directory so its ``*_results.json`` side outputs stay out of the repo root.

Needs ``xlrd`` and ``pdfplumber``, which are not project dependencies::

    uv run --with xlrd --with pdfplumber python scripts/a1_diag/run_owner_scripts.py
    uv run --with xlrd --with pdfplumber python scripts/a1_diag/run_owner_scripts.py \
        --parsed-dir data/parsed_a1diag/fast --label fast


After the three scripts, it writes ``summary.md`` with the one step the owner did by hand in
``reports/a1_measured.md``: the PDF tables' **body cells** and the ``1 - 2*merged/body`` ceiling.
Body cells = ``table_cells`` that are neither ``column_header`` nor ``row_header`` (reproduces the
owner's counts on 6 of 8 tables exactly, +1 cell on the two DOD tables; merged counts on all 8),
and "merged" uses the owner's own ``nums()``, lifted from ``pdf_recall.py`` by ``ast``, not retyped.
"""

from __future__ import annotations

import argparse
import ast
import difflib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = ("erp_compare.py", "erp_lenient.py", "pdf_recall.py")
ROOT_LINE = 'U="/mnt/user-data/uploads/LEDGER/"'
PARSED_PREFIX = "data/parsed/"


def localise(source: str, parsed_dir: str) -> str:
    if source.count(ROOT_LINE) != 1:
        raise SystemExit(f"expected exactly one {ROOT_LINE!r}; the owner's script changed")
    out = source.replace(ROOT_LINE, f"U={REPO.as_posix() + '/'!r}")
    if parsed_dir.rstrip("/") + "/" != PARSED_PREFIX:
        out = out.replace(PARSED_PREFIX, parsed_dir.rstrip("/") + "/")
    return out


def owner_nums(pdf_recall_source: str):
    """The owner's ``nums()`` exactly as written in ``pdf_recall.py`` - same test, not a retype."""
    tree = ast.parse(pdf_recall_source)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "nums")
    namespace: dict = {"re": re}
    exec(ast.get_source_segment(pdf_recall_source, fn), namespace)  # noqa: S102 - owner's code
    return namespace["nums"]


def is_body(cell: dict) -> bool:
    return not cell.get("column_header") and not cell.get("row_header")


def summarise(work: Path, parsed_dir: str, nums) -> str:
    """ERP strict/lenient from the scripts' outputs; PDF ceiling from body cells (a1_measured)."""
    lines = [
        f"# A1 reproduction - `{parsed_dir}`",
        "",
        "## ERP (erp_compare.py, erp_lenient.py)",
        "",
    ]
    lines += [
        "| sheet | GT cells | strict correct | strict % | lenient % | merged rows |",
        "|---|---|---|---|---|---|",
    ]
    erp = json.loads((work / "erp_results.json").read_text(encoding="utf-8"))
    lenient_out = (work / "erp_lenient.py.out").read_text(encoding="utf-8")
    lenient = re.findall(r"^(\S+) (sheet\d): lenient .*? = ([\d.]+)%", lenient_out, re.M)
    lenient_by = {f"{u} {s}": float(p) for u, s, p in lenient}
    tot = ok = 0
    for key, r in erp.items():
        sheet = " ".join(key.split()[:2])
        tot += r["gt_cells"]
        ok += r["correct"]
        lines.append(
            f"| {sheet} | {r['gt_cells']} | {r['correct']} | {r['acc']:.1%} | "
            f"{lenient_by.get(sheet, float('nan')):.1f} % | {r['merged_rows']} |"
        )
    lines += ["", f"**ERP strict total: {ok} / {tot} = {ok / tot:.1%}**", ""]
    lines += ["## PDF tables (pdf_recall.py + body-cell ceiling)", ""]
    lines += [
        "| table | page | all cells | body cells | number recall | merged (all) | merged (body) "
        "| ceiling |",
        "|---|---|---|---|---|---|---|---|",
    ]
    pdf = json.loads((work / "pdf_results.json").read_text(encoding="utf-8"))
    body_tot = num_tot = 0
    for unit, ti, page, _dims, ncells, n_on_page, hit, merged_all, _junk, _extra in pdf:
        doc = json.loads((REPO / parsed_dir / f"{unit}.json").read_text(encoding="utf-8"))
        cells = doc["tables"][ti]["data"]["table_cells"]
        body = [c for c in cells if is_body(c)]
        merged_body = sum(1 for c in body if len(nums(c["text"])) > 1)
        # an upper bound; past 50 % merged it goes negative, which bounds nothing - clamp at 0
        ceiling = max(0, len(body) - 2 * merged_body)
        body_tot += len(body)
        num_tot += ceiling
        lines.append(
            f"| {unit} #/tables/{ti} | {page} | {ncells} | {len(body)} | {hit / n_on_page:.1%} | "
            f"{merged_all} | {merged_body} | {ceiling / len(body):.1%} |"
        )
    lines += [
        "",
        f"**PDF ceiling: {num_tot} / {body_tot} = {num_tot / body_tot:.1%}** · "
        f"**combined: ({ok} + {num_tot}) / ({tot} + {body_tot}) = "
        f"{(ok + num_tot) / (tot + body_tot):.1%}**",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--parsed-dir", default="data/parsed")
    ap.add_argument("--label", default="saved")
    args = ap.parse_args()

    src_dir = REPO / "reports" / "a1_scripts"
    work = REPO / "reports" / "a1_diag" / "repro" / args.label
    work.mkdir(parents=True, exist_ok=True)
    # UTF-8 mode: the scripts open the parsed JSON without an encoding, which is cp1252 on Windows.
    env = dict(os.environ, PYTHONUTF8="1")
    for name in SCRIPTS:
        original = (src_dir / name).read_text(encoding="utf-8")
        copy = localise(original, args.parsed_dir)
        (work / name).write_text(copy, encoding="utf-8")
        diff = [
            line
            for line in difflib.unified_diff(
                original.splitlines(), copy.splitlines(), "owner", "copy", lineterm="", n=0
            )
            if line[:1] in "+-" and line[:3] not in ("+++", "---")
        ]
        print(f"=== {name}: {len(diff) // 2} line(s) changed vs reports/a1_scripts/{name}")
        for line in diff:
            print(f"    {line}")
        run = subprocess.run(
            [sys.executable, name],
            cwd=work,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        (work / f"{name}.out").write_text(run.stdout + run.stderr, encoding="utf-8")
        print(run.stdout)
        if run.returncode:
            print(run.stderr)
            return run.returncode
    nums = owner_nums((src_dir / "pdf_recall.py").read_text(encoding="utf-8"))
    summary = summarise(work, args.parsed_dir, nums)
    (work / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
