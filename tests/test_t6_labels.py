"""T6 label schema and loaders (D-003, D-010, D-044 items 4 and 6(c)); render function (item 7);
pilot config (D-044, status lines of 2026-10-14)."""

import json

import pytest

from ledger.config import load_config
from ledger.eval import labels as L
from ledger.verify import context

MANIFEST = {
    "manifest": True,
    "seed": 1,
    "n": 2,
    "max_claims_per_answer": 3,
    "claims_sha256": "x",
    "sampler": "t6_sample v1",
}


def label_row(cid="q001::c01", qid="q001", label="SUPPORTED", **kw):
    row = {
        "set": "pilot",
        "claim_id": cid,
        "question_id": qid,
        "stratum": "table",
        "label": label,
        "found_positions": [1] if label != "UNSUPPORTED" else [],
        "unsure": False,
        "missing_elements": [],
        "note": "",
        "stands_alone": True,
        "entailed_by_answer": True,
        "assisted": False,
        "context_hash": "h",
    }
    row.update(kw)
    return row


def write(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


def test_pilot_file_loads_slots_and_labels(tmp_path):
    slot = {"set": "pilot", "claim_id": "q002::c01", "question_id": "q002", "stratum": "prose"}
    p = write(tmp_path / "l.jsonl", [MANIFEST, label_row(), {**slot, "label": None}])
    manifest, rows = L.load_pilot_file(p)
    assert manifest.n == 2
    assert isinstance(rows[0], L.PilotLabel) and isinstance(rows[1], L.PilotSlot)
    with pytest.raises(L.LabelsRefused, match="not labelled"):
        L.load_pilot_labels(p)


def test_pilot_loader_refuses_week3_and_panel_rows(tmp_path):
    for bad_set in ("baseline", "post_repair", "panel"):
        bad = label_row("q002::c01", set=bad_set)
        p = write(tmp_path / "l.jsonl", [MANIFEST, label_row(), bad])
        with pytest.raises(L.LabelsRefused, match="not a pilot row"):
            L.load_pilot_file(p)


def test_pilot_loader_refuses_wrong_count_and_duplicates(tmp_path):
    p = write(tmp_path / "l.jsonl", [{**MANIFEST, "n": 3}, label_row(), label_row("q001::c02")])
    with pytest.raises(L.LabelsRefused, match="manifest n"):
        L.load_pilot_file(p)
    p = write(tmp_path / "l.jsonl", [MANIFEST, label_row(), label_row()])
    with pytest.raises(L.LabelsRefused, match="duplicate"):
        L.load_pilot_file(p)
    p = write(tmp_path / "l.jsonl", [label_row(), label_row("q001::c02")])
    with pytest.raises(L.LabelsRefused, match="manifest"):
        L.load_pilot_file(p)


def test_assisted_true_refused():
    with pytest.raises(ValueError):
        L.PilotLabel(**label_row(assisted=True))


def test_partial_needs_missing_element_and_note():
    with pytest.raises(ValueError, match="missing element"):
        L.PilotLabel(**label_row(label="PARTIAL", note="no unit"))
    with pytest.raises(ValueError, match="note"):
        L.PilotLabel(**label_row(label="PARTIAL", missing_elements=["unit"]))
    ok = L.PilotLabel(**label_row(label="PARTIAL", missing_elements=["unit"], note="unit absent"))
    assert ok.label == "PARTIAL"


def test_position_rules():
    with pytest.raises(ValueError, match="position"):
        L.PilotLabel(**label_row(found_positions=[]))
    with pytest.raises(ValueError, match="UNSUPPORTED"):
        L.PilotLabel(**label_row(label="UNSUPPORTED", found_positions=[2]))
    with pytest.raises(ValueError, match="within"):
        L.PilotLabel(**label_row(found_positions=[6]))
    with pytest.raises(ValueError, match="note"):
        L.PilotLabel(**label_row(label="UNSUPPORTED", missing_elements=["period"]))


def paired(qid, half, cid=None):
    return {"set": half, "claim_id": cid or f"{qid}::{half}", "question_id": qid}


def test_paired_loader_refuses_unpaired_halves(tmp_path):
    rows = [
        {**paired("q1", "baseline"), "label": "SUPPORTED", "assisted": False},
        {**paired("q2", "post_repair"), "label": "SUPPORTED", "assisted": False},
    ]
    with pytest.raises(L.LabelsRefused, match="same question ids"):
        L.load_paired_labels(write(tmp_path / "w3.jsonl", rows))
    ok = [
        {**paired("q1", "baseline"), "label": "SUPPORTED", "assisted": False},
        {**paired("q1", "post_repair"), "label": "PARTIAL", "assisted": False},
    ]
    assert len(L.load_paired_labels(write(tmp_path / "w3.jsonl", ok))) == 2


def test_paired_loader_refuses_pilot_rows(tmp_path):
    rows = [
        {**paired("q1", "baseline"), "label": "SUPPORTED", "assisted": False},
        {**paired("q1", "post_repair"), "label": "SUPPORTED", "assisted": False},
        label_row("q001::c01"),
    ]
    with pytest.raises(L.LabelsRefused, match="never pooled"):
        L.load_paired_labels(write(tmp_path / "w3.jsonl", rows))


def test_fold():
    assert L.binary("PARTIAL") == "UNSUPPORTED"
    assert L.binary("PARTIAL", partial_to="SUPPORTED") == "SUPPORTED"
    assert L.binary("SUPPORTED") == "SUPPORTED"
    with pytest.raises(ValueError):
        L.binary("UNSURE")


def test_render_context_is_blank_line_join_no_truncation():
    texts = ["a" * 10_000, "b−c", "d", "e", "f"]
    doc = context.render_context(texts)
    assert doc == "\n\n".join(texts) and len(doc) == sum(map(len, texts)) + 8
    assert context.documents_for("concatenated", texts) == [doc]
    assert context.documents_for("per_chunk_max", texts) == texts
    assert context.context_hash(doc) == context.context_hash("\n\n".join(texts))
    with pytest.raises(ValueError):
        context.documents_for("cited_only", texts)


def test_pilot_config(base_config_path, tmp_path):
    cfg = load_config(base_config_path)
    assert cfg.pilot.default_verifier in cfg.verifier.pilot_candidates
    assert cfg.pilot.max_claims_per_answer == 3 and cfg.pilot.readable_min_each == 8
    assert cfg.decomposition.input_cell == "t5_baseline_r1"
    text = base_config_path.read_text(encoding="utf-8")
    for key in ("pilot_claims", "pilot_min_unsupported"):
        line = next(ln for ln in text.splitlines() if ln.strip().startswith(key + ":"))
        assert "superseded by D-044 items 3 and 5; unused" in line
    override = tmp_path / "o.yaml"
    override.write_text("pilot:\n  default_verifier: some/other\n", encoding="utf-8")
    with pytest.raises(ValueError, match="pilot_candidates"):
        load_config(base_config_path, override)
