"""D-037's one pre-freeze re-chunk — a one-off script, NOT a CLI stage (D-032 Rejected block).

Reads the saved raw Docling export ``data/parsed/<unit>.json`` and the unit's PDF
``data/raw/<source>/<unit>.pdf`` read-only, runs the one chunking path
(``ledger.ingest.parse.chunk_document``: row fix -> markdown-table HybridChunker -> chunk records ->
unit prefix) and writes, per unit, ``<unit>.chunks.jsonl`` and ``<unit>.rowfix.json`` into the
output directory (atomic writes). ``MANIFEST.json`` is written LAST — sha256 and record count per
file, the config hash, the git commit, the tokenizer id — so a directory without it is incomplete.
The output directory may not be ``data/parsed/`` or anything inside it (nor ``data/raw*``).

    uv run python scripts/rechunk_d037.py <out_dir> [--units U ...] [--config override.yaml]

Only ACTIVE manifest rows with a saved export are eligible (D-040). Nothing here computes
``table_chunk_share``; the item-4 output checks are written per unit into the manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from ledger.config import Config, load_config  # noqa: E402
from ledger.ingest.manifest import active_rows, read_manifest  # noqa: E402
from ledger.ingest.parse import (  # noqa: E402
    BAR_REASONS,
    _atomic_write,
    build_chunker,
    chunk_document,
    prefix_category_counts,
    rowfix_json,
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def config_hash(cfg: Config) -> str:
    canon = json.dumps(cfg.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def git_commit(repo: Path) -> dict:
    def run(*args: str) -> str:
        r = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)
        return r.stdout.strip()

    return {"commit": run("rev-parse", "HEAD"), "dirty": bool(run("status", "--porcelain"))}


def refuse_out_dir(out_dir: Path, repo: Path, cfg: Config) -> None:
    """The saved exports and PDFs are never written: out_dir may not be data/parsed/ (or inside
    it), nor data/raw*."""
    out = out_dir.resolve()
    guarded = [(repo / cfg.paths.parsed_dir).resolve()]
    guarded += [p.resolve() for p in (repo / cfg.paths.data_dir).glob("raw*")]
    for g in guarded:
        if out == g or g in out.parents:
            raise SystemExit(f"refused: output directory {out} is {g} or inside it")


def rechunk(
    cfg: Config,
    out_dir: Path,
    *,
    units: list[str] | None = None,
    repo: Path = REPO,
    chunker=None,
) -> dict:
    """Re-chunk ``units`` (default: every ACTIVE unit with a saved export) into ``out_dir``.
    Returns the manifest body (also written to ``out_dir/MANIFEST.json``, last)."""
    refuse_out_dir(out_dir, repo, cfg)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = out_dir / "MANIFEST.json"
    manifest.unlink(missing_ok=True)  # an earlier, now stale manifest would mark this complete
    _, rows = read_manifest(repo / cfg.paths.manifest)
    parsed = repo / cfg.paths.parsed_dir
    active = {r.unit_id: r for r in active_rows(rows) if (parsed / f"{r.unit_id}.json").exists()}
    if units is None:
        units = list(active)
    unknown = [u for u in units if u not in active]
    if unknown:
        raise SystemExit(f"not ACTIVE units with a saved export: {unknown}")
    chunker = chunker or build_chunker(cfg)
    files: dict[str, dict] = {}
    checks: dict[str, dict] = {}
    for uid in units:
        row = active[uid]
        doc_dict = json.loads((parsed / f"{uid}.json").read_text(encoding="utf-8"))
        pdf = repo / cfg.paths.raw_dir / row.source / f"{uid}.pdf"
        unit = chunk_document(doc_dict, pdf, row, cfg, chunker=chunker)
        chunks_p, rowfix_p = out_dir / f"{uid}.chunks.jsonl", out_dir / f"{uid}.rowfix.json"
        _atomic_write(
            chunks_p, "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in unit.records)
        )
        _atomic_write(rowfix_p, rowfix_json(uid, unit.fix_log))
        files[chunks_p.name] = {"sha256": sha256(chunks_p), "records": len(unit.records)}
        files[rowfix_p.name] = {"sha256": sha256(rowfix_p), "records": len(unit.fix_log)}
        c = dict(unit.checks)  # item 4 as amended by D-037 status 2026-10-02 (rulings 2, 3)
        c["prefix_categories"] = prefix_category_counts(unit.sources)
        tables = [r for r in unit.records if r["chunk_type"] == "table"]
        c["question_source_barred"] = {
            "slices": sum(1 for r in tables if r["question_source_barred"]["barred"]),
            "tables": len({r["item"] for r in tables if r["question_source_barred"]["barred"]}),
            "slices_by_reason": {
                why: sum(1 for r in tables if why in r["question_source_barred"]["reasons"])
                for why in BAR_REASONS
            },
            "tables_by_reason": {
                why: sorted(
                    {r["item"] for r in tables if why in r["question_source_barred"]["reasons"]}
                )
                for why in BAR_REASONS
            },
        }
        c["max_n_tokens_table"] = max(
            (r["n_tokens"] for r in unit.records if r["chunk_type"] == "table"), default=0
        )
        c["max_n_tokens_all"] = max((r["n_tokens"] for r in unit.records), default=0)
        checks[uid] = c
    tok = chunker.tokenizer
    body = {
        "script": "scripts/rechunk_d037.py",
        "decision": "D-037 (one pre-freeze re-chunk)",
        "units": units,
        "files": files,
        "config_hash": config_hash(cfg),
        "chunking": cfg.chunking.model_dump(mode="json"),
        "git": git_commit(repo),
        "tokenizer": {
            "id": cfg.embedding.model,
            "class": type(tok).__name__,
            "name_or_path": getattr(tok.get_tokenizer(), "name_or_path", None),
            "max_tokens": tok.get_max_tokens(),
        },
        "d037_item4_checks": checks,
    }
    _atomic_write(manifest, json.dumps(body, ensure_ascii=False, indent=1))
    return body


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--units", nargs="+", default=None)
    ap.add_argument("--config", default=None, help="override YAML deep-merged onto base.yaml")
    a = ap.parse_args(argv)
    cfg = load_config(REPO / "configs" / "base.yaml", a.config)
    body = rechunk(cfg, a.out_dir, units=a.units)
    for uid, c in body["d037_item4_checks"].items():
        print(
            f"{uid}: table slices {c['table_slices']} | header-row missing "
            f"{len(c['header_row_missing'])} (tables {len(c['header_not_repeated'])}) | "
            f"prefix_integrity {len(c['prefix_integrity'])} | unit line missing "
            f"{len(c['unit_line_missing'])} | titles printed "
            f"{c['title_printed_by_prefix']['slices']} | body lines not '|' "
            f"{len(c['body_line_not_pipe'])} | blank/partial headers {len(c['blank_headers'])}/"
            f"{len(c['partial_headers'])} | barred slices {c['question_source_barred']['slices']}"
            f" | max table tokens {c['max_n_tokens_table']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
