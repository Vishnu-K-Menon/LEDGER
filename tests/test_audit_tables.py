"""A1 sheet machinery: the UTF-16 parse log, warning attribution by parse window, the coverage
rule, and the ``column_header`` flags. No parsed corpus is needed - fixtures stand in for it."""

from pathlib import Path
from types import SimpleNamespace

from ledger.config import load_config
from ledger.ingest.audit_pages import header_flags, numeric_row, rows_of
from ledger.ingest.audit_tables import DroppedWarning, read_log_text, wanted, warnings_by_unit

LOG = """[2026-09-25 21:35:45] parse start: 19 units in scope | workers=1
[2026-09-25 21:35:52] PARSED  [1/19] cbo-59848 | 2p | 5.8s | 0.344 p/s | chunks=9
2026-09-25 22:56:58,432 MatchingPostProcessor WARNING  11 of 532 pdf cells matched neither a row \
nor a column band of the 49x7 grid and were dropped from the table
2026-09-25 22:57:25,097 MatchingPostProcessor WARNING  6 of 484 pdf cells matched neither a row \
nor a column band of the 49x8 grid and were dropped from the table
[2026-09-25 22:59:32] PARSED  [2/19] govinfo-BUDGET-2026-DOD | 114p | 2196.7s | chunks=2445
[2026-09-25 23:31:49] PARSED  [3/19] govinfo-BUDGET-2027-FCS | 120p | 1936.0s | chunks=2011
"""


def write_log(tmp_path: Path, encoding: str) -> Path:
    logs = tmp_path / "logs"
    logs.mkdir(parents=True)
    path = logs / "parse_2026-09-25.log"
    path.write_bytes(LOG.encode(encoding))
    return path


def test_read_log_text_handles_utf16(tmp_path):
    """PowerShell Tee-Object writes UTF-16; grep and a naive read find nothing in it."""
    for encoding in ("utf-8", "utf-16", "utf-16-le"):
        path = write_log(tmp_path / encoding, encoding)
        assert "MatchingPostProcessor" in read_log_text(path)


def test_warnings_attributed_to_the_unit_that_follows(tmp_path):
    """A warning belongs to the unit whose PARSED line closes its window, not the previous one."""
    write_log(tmp_path, "utf-16")
    cfg = load_config()
    got = warnings_by_unit(cfg, tmp_path)
    assert [w.dropped for w in got["govinfo-BUDGET-2026-DOD"]] == [11, 6]
    assert got.get("cbo-59848", []) == []
    assert got.get("govinfo-BUDGET-2027-FCS", []) == []


def test_no_log_is_not_an_error(tmp_path):
    assert warnings_by_unit(load_config(), tmp_path) == {}


def test_coverage_rule_reads_unit_ids_from_config():
    """D31: the audited units live in configs/base.yaml, not in the code."""
    cfg = load_config()
    assert wanted(cfg, "govinfo-BUDGET-2026-DOD") == 2
    assert wanted(cfg, "cbo-61959") == 1  # via the `cbo-*` pattern
    assert wanted(cfg, "eia-pdf-sec13") == 0


def cell(row, col, text, header=False):
    return SimpleNamespace(
        start_row_offset_idx=row, start_col_offset_idx=col, text=text, column_header=header
    )


def test_header_flags_and_rows():
    tbl = SimpleNamespace(
        data=SimpleNamespace(
            table_cells=[
                cell(0, 0, "Year", True),
                cell(0, 1, "Percent", True),
                cell(1, 0, "1975"),
                cell(1, 1, "0.9"),
            ]
        )
    )
    assert header_flags(tbl) == (1, True)
    assert rows_of(tbl) == {0: ["Year", "Percent"], 1: ["1975", "0.9"]}


def test_header_not_at_row_zero_is_flagged():
    """A markdown serializer repeats the header rows at the top; a later header has none."""
    tbl = SimpleNamespace(
        data=SimpleNamespace(table_cells=[cell(0, 0, "continued"), cell(2, 0, "Year", True)])
    )
    assert header_flags(tbl) == (1, False)


def test_numeric_row():
    assert numeric_row(["1975", "0.9", "8.2", "6.7"])
    assert not numeric_row(["Year or quarter", "Net exports", "Total"])


def test_dropped_warning_render():
    assert DroppedWarning("t", 11, 532, 49, 7).render() == "11 of 532 pdf cells (49x7 grid)"
