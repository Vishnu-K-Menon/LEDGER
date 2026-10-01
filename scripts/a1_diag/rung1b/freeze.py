"""D-039: the fresh oracle freeze. Written once, before any rung-1b output exists; asserted by the
rung-1b evaluator before it scores anything (``assert_frozen()``), and by the local test
``tests/test_fresh_freeze.py`` (skipped without the local data).

Covers: the admission files (MER / ERP cells, the table list, the STEO aug26 cells), the
clause-(b) checker, the oracle code and STEO admission rule, the fresh scan, the admission builder,
the fresh manifests, and every export / granule xls the admission read (against the sha256 the
manifests recorded at fetch). Text files are hashed with line endings normalised (CRLF -> LF), so
a Windows checkout and a Linux clone agree; binary files are hashed as bytes.

    uv run python scripts/a1_diag/rung1b/freeze.py --write     # once, at the freeze
    uv run python scripts/a1_diag/rung1b/freeze.py --check
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
FREEZE = REPO / "data" / "oracle" / "fresh" / "freeze.json"
GROUPS = {
    "admission": [
        "data/oracle/fresh/admission/mer_cells.jsonl",
        "data/oracle/fresh/admission/erp_cells.jsonl",
        "data/oracle/fresh/admission/tables.json",
        "data/oracle/fresh/steo/cells.jsonl",
    ],
    "checker": ["scripts/a1_diag/rung1b/f5_sizing.py", "scripts/a1_diag/rung1b/f5_dump.py"],
    "oracle": [
        "scripts/a1_diag/oracle.py",
        "scripts/a1_diag/steo.py",
        "data/oracle/steo/2026-09/admission_rule.md",
    ],
    "scan": ["scripts/a1_diag/rung1b/fresh_oracle.py"],
    "builder": ["scripts/a1_diag/rung1b/fresh_admission.py"],
    "manifests": [
        "data/oracle/fresh/mer/sources.json",
        "data/oracle/fresh/erp/sources.json",
        "data/oracle/fresh/steo/sources.json",
        "data/oracle/fresh/erp_draw.json",
    ],
}
TEXT = (".py", ".json", ".jsonl", ".md")


def digest(rel: str) -> str:
    b = (REPO / rel).read_bytes()
    if rel.endswith(TEXT):
        b = b.replace(b"\r\n", b"\n")
    return hashlib.sha256(b).hexdigest()


def source_files() -> dict[str, str]:
    """Every export / xls the admission read, with the sha256 recorded at fetch (raw bytes)."""
    out = {}
    mer = json.loads((REPO / "data/oracle/fresh/mer/sources.json").read_text(encoding="utf-8"))
    used = {p["export"] for p in mer["pages"] if p.get("title_match")}
    for x in mer["exports"].values():
        if x["url"].split("tbl=")[1] in used and x.get("export_title"):
            out[x["path"]] = x["sha256"]
    erp = json.loads((REPO / "data/oracle/fresh/erp/sources.json").read_text(encoding="utf-8"))
    for g in erp["granules"].values():
        out[g["xls_path"]] = g["xls_sha256"]
    return out


def current() -> dict:
    return {
        "groups": {k: {rel: digest(rel) for rel in v} for k, v in GROUPS.items()},
        "sources": {
            rel: hashlib.sha256((REPO / rel).read_bytes()).hexdigest() for rel in source_files()
        },
    }


def assert_frozen() -> None:
    """The evaluator-path assert: every frozen file is byte-identical to the freeze."""
    frozen = json.loads(FREEZE.read_text(encoding="utf-8"))
    now = current()
    bad = [
        f"{g}:{rel}"
        for g, files in frozen["groups"].items()
        for rel, h in files.items()
        if now["groups"].get(g, {}).get(rel) != h
    ]
    bad += [f"source:{rel}" for rel, h in frozen["sources"].items() if now["sources"].get(rel) != h]
    recorded = source_files()
    bad += [
        f"source-vs-manifest:{rel}"
        for rel, h in recorded.items()
        if frozen["sources"].get(rel) != h
    ]
    assert not bad, f"fresh oracle freeze broken ({len(bad)}): {bad[:10]}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if args.write:
        body = current()
        mismatch = [r for r, h in source_files().items() if body["sources"][r] != h]
        assert not mismatch, f"export / xls differs from its fetch record: {mismatch}"
        body["note"] = (
            "D-039 fresh oracle freeze; written before any rung-1b output exists; "
            "text hashed with CRLF -> LF"
        )
        FREEZE.write_text(json.dumps(body, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(
            f"frozen: {sum(len(v) for v in body['groups'].values())} files + "
            f"{len(body['sources'])} export/xls sources"
        )
    if args.check or not args.write:
        assert_frozen()
        print("freeze OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
