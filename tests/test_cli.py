import pytest

from ledger.cli import build_parser, main

SUBCOMMANDS = [
    "ingest",
    "audit-tables",
    "index",
    "loadtest",
    "baseline",
    "questions",
    "pilot",
    "matrix",
    "eval",
    "kappa",
    "audit-decomp",
    "smoke",
]


def test_all_subcommands_registered():
    parser = build_parser()
    sub = next(a for a in parser._actions if a.dest == "command")
    assert set(sub.choices) == set(SUBCOMMANDS)


@pytest.mark.parametrize("argv", [["--help"]] + [[c, "--help"] for c in SUBCOMMANDS])
def test_help_exits_zero(argv, capsys):
    with pytest.raises(SystemExit) as exc:
        main(argv)
    assert exc.value.code == 0
    assert "usage: ledger" in capsys.readouterr().out


@pytest.mark.parametrize(
    "argv",
    [
        ["ingest", "--limit", "20"],
        ["ingest", "--all", "--confirmed"],
        ["audit-tables", "--n", "10"],
        ["index"],
        ["loadtest"],
        ["baseline", "--questions", "data/questions_draft.jsonl"],
        ["questions", "--n", "200", "--controls", "20"],
        ["pilot", "--labels", "data/labels_pilot.jsonl"],
        ["matrix", "--seed", "1"],
        ["matrix", "--seed", "2", "--confirm-seed-1-inspected"],
        ["eval", "results/"],
        ["kappa", "--labels", "data/labels_week3.jsonl"],
        ["audit-decomp", "--answers", "run", "--n", "25"],
        ["smoke"],
    ],
)
def test_bodies_not_implemented(argv):
    with pytest.raises(NotImplementedError):
        main(argv)


def test_matrix_seed_flag_guard():
    """D-009: seeds other than 1 require --confirm-seed-1-inspected."""
    with pytest.raises(SystemExit) as exc:
        main(["matrix", "--seed", "2"])
    assert exc.value.code == 2


def test_ingest_all_requires_confirmed():
    """D-001 guard shape."""
    with pytest.raises(SystemExit) as exc:
        main(["ingest", "--all"])
    assert exc.value.code == 2
