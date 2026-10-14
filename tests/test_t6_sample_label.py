"""T6 sampler (D-044 item 3), label tool (item 4; status 2026-10-14 (2)), panel (item 10) and the
git guards. Git is stubbed; tmp_path only; no real data."""

from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path

import pytest

from ledger.claims.schema import ClaimRecord
from ledger.eval.labels import PilotLabel, load_pilot_file, load_pilot_labels
from ledger.pilot import label_tool as T
from ledger.pilot import repo
from ledger.pilot.panel import validate_panel
from ledger.pilot.sample import (
    SampleRefused,
    manifest_for,
    render_lines,
    sample_slots,
    strata,
    write_slots,
)
from ledger.verify.context import context_hash, render_context


def rec(qid, n, kept=True, stratum="table"):
    return ClaimRecord(
        claim_id=f"{qid}::c{n:02d}",
        question_id=qid,
        stratum=stratum,
        text=f"{qid} claim {n} is 5.",
        source_sentence_idx=0,
        qualifiers={"entity": "", "unit": "", "period": ""},
        citations=["k2"],
        kept=kept,
    )


RECORDS = (
    [rec("q001", i) for i in range(1, 6)]  # 5 claims -> 3 drawn
    + [rec("q002", i, stratum="prose") for i in range(1, 3)]  # 2 -> both kept
    + [rec("q003", 1), rec("q003", 2, kept=False)]  # dropped claims never sampled
)


# ---- sampler --------------------------------------------------------------------------------


def test_sample_reproducible_and_capped():
    a = sample_slots(RECORDS, seed=7, max_per=3)
    b = sample_slots(RECORDS, seed=7, max_per=3)
    assert a == b
    per_q = {}
    for s in a:
        per_q.setdefault(s["question_id"], []).append(s["claim_id"])
    assert len(per_q["q001"]) == 3
    assert sorted(per_q["q002"]) == ["q002::c01", "q002::c02"]
    assert per_q["q003"] == ["q003::c01"]
    assert strata(a) == {"prose": 2, "table": 4}
    assert all(s["label"] is None and s["set"] == "pilot" for s in a)
    assert sample_slots(RECORDS, seed=8, max_per=3) != a  # the seed matters


def test_write_slots_idempotent_and_never_overwrites(tmp_path):
    slots = sample_slots(RECORDS, seed=7, max_per=3)
    m = manifest_for(slots, seed=7, max_per=3, claims_sha="abc")
    p = tmp_path / "labels.jsonl"
    assert write_slots(p, m, slots) == "written"
    assert write_slots(p, m, slots) == "unchanged"
    with pytest.raises(SampleRefused, match="different draw"):
        write_slots(p, m, sample_slots(RECORDS, seed=8, max_per=3))
    manifest, rows = load_pilot_file(p)
    assert manifest.n == 6
    labelled = [r.model_dump(mode="json") for r in rows]
    labelled[0] = label_row(labelled[0])
    p.write_bytes(render_lines(manifest.model_dump(mode="json"), labelled))
    with pytest.raises(SampleRefused, match="holds labels"):
        write_slots(p, m, slots)


def label_row(slot, label="SUPPORTED"):
    return {
        **slot,
        "label": label,
        "found_positions": [2],
        "unsure": False,
        "missing_elements": [],
        "note": "",
        "stands_alone": True,
        "entailed_by_answer": True,
        "assisted": False,
        "context_hash": "h",
    }


# ---- display --------------------------------------------------------------------------------


class Stream(io.StringIO):
    def __init__(self, tty, encoding):
        super().__init__()
        self._tty, self._enc = tty, encoding

    def isatty(self):
        return self._tty

    @property
    def encoding(self):
        return self._enc


def test_console_check():
    T.check_console(Stream(True, "utf-8"))
    for tty, enc in ((False, "utf-8"), (True, "cp1252"), (False, "cp1252")):
        with pytest.raises(T.LabelToolRefused, match="UTF-8 console"):
            T.check_console(Stream(tty, enc))


def test_legend_names_lookalikes():
    lg = T.legend("was −106.3, –106.3 and -106.3 �� a b")
    assert "U+2212 MINUS SIGN x1" in lg and "U+2013 EN DASH x1" in lg
    assert "U+FFFD REPLACEMENT CHARACTER x2" in lg and "U+00A0 NO-BREAK SPACE x1" in lg
    assert T.legend("plain ascii - 5") == ""
    assert all(f"U+{ord(c):04X}" in T.self_test_text() for c in T.SELF_TEST_CHARS)


# ---- label tool ---------------------------------------------------------------------------------

CHUNKS = ["pos one text", "pos two 5 – dash", "three", "four", "five"]
CHUNK_IDS = ["unit-A::p1::tbl-0::s0", "k2", "unit-B::p3::t::s1", "k4", "k5"]
QUESTION = "What was the secret question text?"


def item(cid="q001::c01"):
    claims = {cid: rec("q001", int(cid[-2:]))}
    contexts = {
        "q001": {
            "question": QUESTION,
            "chunks": [{"chunk_id": i, "text": t} for i, t in zip(CHUNK_IDS, CHUNKS, strict=True)],
        }
    }
    slot = load_slot(cid)
    return T.build_items([slot], claims, contexts, {"q001": "The answer says 5."})[0]


def load_slot(cid):
    from ledger.eval.labels import PilotSlot

    return PilotSlot(set="pilot", claim_id=cid, question_id="q001", stratum="table")


def test_screen_hides_question_ids_and_verifier():
    it = item()
    s = T.screen_one(it, 1, 3)
    assert it.claim in s and all(t in s for t in CHUNKS)
    assert "The answer cited position(s): 2" in s
    assert QUESTION not in s and not any(cid in s for cid in CHUNK_IDS)
    assert "::" not in s and "gold" not in s.lower() and "verifier" not in s.lower()
    assert "The answer says 5." not in s  # the answer is shown only at screen 3
    assert it.context_hash == context_hash(render_context(CHUNKS))


class Script:
    def __init__(self, answers):
        self.answers, self.prompts, self.said = list(answers), [], []

    def ask(self, prompt):
        self.prompts.append(prompt)
        return self.answers.pop(0)

    def say(self, text):
        self.said.append(text)


def test_label_one_answer_shown_only_after_lock():
    sc = Script(["p", "2", "u", "unit not stated", "n", "y", "y", "y"])
    row = T.label_one(item(), sc.ask, sc.say)
    assert row["label"] == "PARTIAL" and row["missing_elements"] == ["unit"]
    assert row["entailed_by_answer"] is True and row["assisted"] is False
    lock_at = next(i for i, p in enumerate(sc.prompts) if p.startswith("Lock"))
    alone_at = next(i for i, p in enumerate(sc.prompts) if "stand alone" in p)
    assert alone_at < lock_at
    shown = next(i for i, t in enumerate(sc.said) if "The answer says 5." in t)
    assert all("The answer says 5." not in t for t in sc.said[:shown])
    PilotLabel(**row)


def test_label_one_redo_and_validation():
    # PARTIAL with an empty note is not accepted -> redo; then 'r' redoes; then UNSUPPORTED
    sc = Script(
        [
            "p",
            "1",
            "e",
            "",
            "n",
            "y",  # rejected: PARTIAL needs a note
            "s",
            "1",
            "",
            "n",
            "y",
            "r",  # redo requested
            "x",
            "u",
            "",
            "",
            "y",
            "n",
            "y",
            "n",
        ]
    )
    row = T.label_one(item(), sc.ask, sc.say)
    assert row["label"] == "UNSUPPORTED" and row["found_positions"] == [] and row["unsure"]
    assert row["entailed_by_answer"] is False
    assert any("Not accepted" in t for t in sc.said)


def write_labels(tmp_path, ids):
    slots = [load_slot(c).model_dump(mode="json") for c in ids]
    m = manifest_for(slots, seed=1, max_per=3, claims_sha="abc")
    p = tmp_path / "labels.jsonl"
    p.write_bytes(render_lines(m, slots))
    return p


def test_run_session_resumes_and_persists(tmp_path):
    p = write_labels(tmp_path, ["q001::c01", "q001::c02"])
    items = [item("q001::c01"), item("q001::c02")]
    one = ["s", "2", "", "n", "y", "y", "y"]
    with pytest.raises(IndexError):  # interrupted during the second row
        T.run_session(p, items, Script(one + ["s"]).ask, lambda _: None)
    _, rows = load_pilot_file(p)
    assert isinstance(rows[0], PilotLabel) and not isinstance(rows[1], PilotLabel)
    sc = Script(one)
    assert T.run_session(p, items, sc.ask, sc.say) == 1
    assert "Claim 2 of 2" in sc.said[0]  # resumed at the first unlabelled row
    _, labelled = load_pilot_labels(p)
    assert [r.claim_id for r in labelled] == ["q001::c01", "q001::c02"]


def fake_git(committed: dict[str, bytes | None], head_files: dict[str, str] | None = None):
    def run(args):
        cmd = args[0]
        if cmd == "ls-files":
            ok = args[-1] in committed
            return subprocess.CompletedProcess(args, 0 if ok else 1, "", "")
        if cmd == "diff":
            path = args[-1]
            same = committed.get(path) is not None and Path(path).read_bytes() == committed[path]
            return subprocess.CompletedProcess(args, 0 if same else 1, "", "")
        if cmd == "show":
            path = args[1].split(":", 1)[1]
            text = (head_files or {}).get(path)
            return subprocess.CompletedProcess(args, 0 if text else 128, text or "", "")
        raise AssertionError(args)

    return run


def test_preflight_guards(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = write_labels(Path("."), ["q001::c01"])
    guide = Path("guide.md")
    guide.write_text("SUPPORTED means ...\n", encoding="utf-8")
    lp, gp = p.as_posix(), guide.as_posix()
    with pytest.raises(T.LabelToolRefused, match="guide.md must be committed"):
        T.preflight(p, guide, fake_git({}))
    with pytest.raises(T.LabelToolRefused, match="ids must be committed"):
        T.preflight(p, guide, fake_git({gp: guide.read_bytes()}))
    run = fake_git({gp: guide.read_bytes(), lp: p.read_bytes()}, {lp: p.read_text()})
    sha = T.preflight(p, guide, run)
    manifest, _ = load_pilot_file(p)
    assert manifest.label_guide_sha256 == sha == repo.sha256_file(guide)
    guide.write_text("changed\n", encoding="utf-8")
    run = fake_git({gp: guide.read_bytes(), lp: b""}, {lp: p.read_text()})
    with pytest.raises(T.LabelToolRefused, match="changed since labelling started"):
        T.preflight(p, guide, run)


def test_dirty_parsing():
    out = " M ledger/x.py\n?? scripts/new.py\n?? notes.txt\nA  data/y.jsonl\n"

    def run(args):
        return subprocess.CompletedProcess(args, 0, out, "")

    assert repo.dirty(run, ["scripts"]) == ["ledger/x.py", "scripts/new.py", "data/y.jsonl"]


# ---- panel --------------------------------------------------------------------------------


def test_panel_validation(tmp_path):
    row = {
        "set": "panel",
        "panel_id": "p01",
        "question_id": "q001",
        "claim": "In 2024 it was 5.",
        "swap": "period",
        "note": "2025 -> 2024",
        "constructed": True,
    }
    p = tmp_path / "panel.jsonl"
    p.write_text(
        json.dumps(row)
        + "\n"
        + json.dumps({**row, "panel_id": "p02", "question_id": "q003"})
        + "\n"
    )
    rows, problems = validate_panel(p, ["q001"])
    assert len(rows) == 2 and problems == ["p02: q003 is not a run-1 non-abstaining answer"]
    p.write_text(json.dumps({**row, "constructed": False}) + "\n")
    assert validate_panel(p, ["q001"])[1][0].startswith("schema")
    p.write_text(json.dumps(row) + "\n")
    from ledger.eval.labels import LabelsRefused, load_paired_labels

    with pytest.raises(LabelsRefused):
        load_paired_labels(p)
