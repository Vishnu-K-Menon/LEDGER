"""scripts/t5_report.py with contexts but no Batch result: only A6 is written, exit 0."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

from ledger.baseline.run import RunRecord

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "t5_report.py"


def _load():
    spec = importlib.util.spec_from_file_location("t5_report_script", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fake(mod, monkeypatch, tmp_path, runs, written):
    ctx = tmp_path / "contexts.jsonl"
    ctx.write_text("", encoding="utf-8")
    cfg = SimpleNamespace(
        paths=SimpleNamespace(results_dir=tmp_path, chunks=tmp_path / "chunks.jsonl"),
        generator=SimpleNamespace(output_mode="structured_output"),
        retrieval=SimpleNamespace(k_dense=30),
    )
    (tmp_path / "t5").mkdir()
    for n in ("primary", "card"):
        (tmp_path / "t5" / f"retrieval_{n}.jsonl").write_text("", encoding="utf-8")
    (tmp_path / "t5" / "contexts.jsonl").write_text("", encoding="utf-8")
    monkeypatch.setattr(mod, "load_config", lambda override=None: cfg)
    monkeypatch.setattr(mod, "read_questions", lambda p: [])
    monkeypatch.setattr(mod, "read_chunks", lambda p: [])
    monkeypatch.setattr(mod, "git_commit", lambda p: "deadbeef")
    monkeypatch.setattr(mod, "lf_sha256", lambda p: "0" * 64)
    monkeypatch.setattr(mod, "read_arm_file", lambda p: [])
    monkeypatch.setattr(mod, "read_contexts", lambda p: [])
    monkeypatch.setattr(mod, "load_runs", lambda *a, **k: runs)
    monkeypatch.setattr(mod, "CONTROLS", tmp_path / "no_controls.json")
    monkeypatch.setattr(mod.rp, "composition_block", lambda *a, **k: "")
    monkeypatch.setattr(mod.rp, "a6_report", lambda *a, **k: "A6")
    monkeypatch.setattr(mod.rp, "finish", lambda text, comp: text)
    monkeypatch.setattr(mod, "_write", lambda name, text: written.append(name))


def test_no_batch_result_writes_only_a6_and_exits_zero(monkeypatch, tmp_path, capsys):
    mod = _load()
    written: list[str] = []
    missing = [RunRecord(1, "q001", "missing", None, [], {}, None, "no result")]
    _fake(mod, monkeypatch, tmp_path, missing, written)
    assert mod.main([]) == 0
    assert written == ["t5_a6.md"]
    assert "no request has a Batch result" in capsys.readouterr().out
