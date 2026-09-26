"""CLI output must survive a console that cannot encode the report characters, and the parse
footer must not print a rate when nothing was parsed this run (both found on the T3 overnight run).
"""

import io
import sys

from ledger.cli import format_rate, tolerant_stdio


def cp1252_stdout() -> io.TextIOWrapper:
    """A stdout like the one that aborted the T3 run: cp1252, strict by default."""
    return io.TextIOWrapper(io.BytesIO(), encoding="cp1252", newline="")


def test_cp1252_stdout_raises_without_the_fix():
    """The failure being fixed: U+2265 is the character that killed the overnight run."""
    out = cp1252_stdout()
    try:
        out.write("threshold >= 0.95 ≥ band")
        out.flush()
    except UnicodeEncodeError:
        return
    raise AssertionError("expected UnicodeEncodeError on a strict cp1252 stream")


def test_tolerant_stdio_survives_cp1252(monkeypatch):
    """After ``tolerant_stdio`` the same write is replaced, not raised."""
    out, err = cp1252_stdout(), cp1252_stdout()
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)
    tolerant_stdio()
    print("≥ 0.95 · table_chunk_share — A9")  # >=, middot, em dash
    print("stderr ≥", file=sys.stderr)
    sys.stdout.flush()
    sys.stderr.flush()
    written = out.buffer.getvalue().decode("cp1252")
    assert "0.95" in written and "table_chunk_share" in written
    assert "≥" not in written  # replaced, not encoded


def test_tolerant_stdio_ignores_streams_without_reconfigure(monkeypatch):
    """A captured or detached stream (pytest's own, a pipe wrapper) must not break the CLI."""
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    monkeypatch.setattr(sys, "stderr", io.StringIO())
    tolerant_stdio()  # no exception


def test_format_rate_guards_the_division():
    """A resumed run parses 0 pages in ~0 s; the old expression printed 366111283.15 pages/s."""
    assert format_rate(0, 0.0) == "n/a"
    assert format_rate(659, 0.0) == "n/a"
    assert format_rate(0, 8116.1) == "n/a"
    assert format_rate(659, 8116.1) == "0.08 pages/s"
