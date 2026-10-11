"""Writes data/t5_review_packet.md: every drafted T5 candidate with its chunk text, in draw order,
for pasting into a separate checking chat. Read-only on the candidates file. Run from LEDGER:
    uv run --no-sync python "$env:TEMP\\t5_export_packet.py"
"""

import json
from pathlib import Path

latest = {}
for ln in Path("data/questions_draft_candidates.jsonl").read_text(encoding="utf-8").splitlines():
    if ln.strip():
        r = json.loads(ln)
        latest[r["candidate_id"]] = r
chunks = {}
for ln in Path("data/chunks.jsonl").read_text(encoding="utf-8").splitlines():
    if ln.strip():
        r = json.loads(ln)
        chunks[r["chunk_id"]] = r
units = []
for ln in Path("data/manifest.jsonl").read_text(encoding="utf-8").splitlines():
    if ln.strip():
        r = json.loads(ln)
        if r.get("status") == "ACTIVE":
            units.append(f"- {r.get('unit_id')} | {r.get('source')} | {r.get('date_issued')} | {r.get('title')}")

order = {"table": 0, "prose": 1, "supplement": 2, "control": 3}
rows = sorted(latest.values(), key=lambda r: (order[r["stratum"]], r.get("supp_source", ""), r["order_index"]))
out = ["# T5 candidate review packet", "", f"{len(rows)} candidates, in draw order.", ""]
for c in rows:
    out.append(f"## {c['candidate_id']} | {c['stratum']} #{c['order_index'] + 1} | {c.get('tier', '')}")
    if "error" in c:
        out += ["DRAFT FAILED (no question). Verdict must be r.", "CHUNK:", "```",
                chunks.get(c["chunk_id"], {}).get("text", "(missing)"), "```", ""]
        continue
    if c["stratum"] == "control":
        out += [f"QUESTION: {c['question']}", f"KIND: {c['control_kind']}",
                f"RATIONALE: {c.get('rationale', '')}", ""]
        continue
    ch = chunks.get(c["chunk_id"], {})
    out += [f"SOURCE: {c.get('source')} / {c.get('unit_id')} / {c['chunk_id']}",
            f"QUESTION: {c['question']}", f"GOLD: {c['gold_answer']!r} ({c['answer_type']})",
            "CHUNK:", "```", ch.get("text", "(missing)"), "```", ""]
out += ["# Corpus documents (for judging the controls)", ""] + units
Path("data/t5_review_packet.md").write_text("\n".join(out) + "\n", encoding="utf-8")
print(f"wrote data/t5_review_packet.md ({len(rows)} candidates)")
