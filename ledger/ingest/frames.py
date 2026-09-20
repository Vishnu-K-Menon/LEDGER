"""CBO sampling frames (D-034). cbo.gov is behind DataDome and is NEVER fetched by script; the
owner captured ``data/frames/frame_<year>.html`` in a browser (see ``data/frames/README.yaml``).
This module parses those files into ``data/frames/cbo_candidates.csv`` so the seeded draw's
input is a committed artifact, not a re-parse."""

from __future__ import annotations

import csv
import re
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from pathlib import Path

FRAME_YEARS = (2023, 2024, 2025, 2026)
EXPECTED_PER_FRAME = 10
CSV_FIELDS = ["frame_year", "publication_id", "page_url", "date_issued", "type", "title"]
_PUB_RE = re.compile(r"https://www\.cbo\.gov/publication/(\d+)$")


@dataclass(frozen=True)
class CboCandidate:
    frame_year: int
    publication_id: str
    page_url: str
    date_issued: str
    type: str
    title: str


class _RowParser(HTMLParser):
    """Walks ``<li class="views-row">`` blocks: title anchor, type span, <time datetime>."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[dict[str, str]] = []
        self._depth = 0  # nesting inside a views-row li
        self._cur: dict[str, str] | None = None
        self._capture: str | None = None
        self._in_type = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class", "")
        if tag == "li" and "views-row" in cls:
            self._cur = {}
            self._depth = 1
            return
        if self._cur is None:
            return
        if tag in ("li", "ul", "ol", "div", "span", "h3", "p"):
            self._depth += 1
        if tag == "a" and "href" in a and _PUB_RE.match(a["href"]) and "page_url" not in self._cur:
            self._cur["page_url"] = a["href"]
            self._cur["publication_id"] = _PUB_RE.match(a["href"]).group(1)
            self._capture = "title"
            self._cur["title"] = ""
        elif tag == "span" and "views-field-type" in cls:
            self._in_type = True
        elif tag == "span" and self._in_type and "field-content" in cls:
            self._capture = "type"
            self._cur["type"] = ""
        elif tag == "time" and "datetime" in a:
            self._cur["date_issued"] = a["datetime"][:10]

    def handle_endtag(self, tag):
        if self._cur is None:
            return
        if tag == "a" and self._capture == "title":
            self._capture = None
        elif tag == "span" and self._capture == "type":
            self._capture = None
            self._in_type = False
        if tag in ("li", "ul", "ol", "div", "span", "h3", "p"):
            self._depth -= 1
            if tag == "li" and self._depth <= 0:
                self.rows.append(self._cur)
                self._cur = None

    def handle_data(self, data):
        if self._cur is not None and self._capture:
            self._cur[self._capture] += data


def parse_frame(path: Path, year: int) -> list[CboCandidate]:
    p = _RowParser()
    p.feed(path.read_text(encoding="utf-8", errors="replace"))
    out: list[CboCandidate] = []
    seen: set[str] = set()
    for r in p.rows:
        if "publication_id" not in r or r["publication_id"] in seen:
            continue
        seen.add(r["publication_id"])
        out.append(
            CboCandidate(
                frame_year=year,
                publication_id=r["publication_id"],
                page_url=r["page_url"],
                date_issued=r.get("date_issued", ""),
                type=" ".join(r.get("type", "").split()),
                title=" ".join(r.get("title", "").split()),
            )
        )
    return out


def parse_frames(frames_dir: Path) -> list[CboCandidate]:
    """All four frames; raises if any frame does not have exactly 10 distinct candidates or the
    union is not 40 distinct — the files changed since the owner verified them."""
    all_rows: list[CboCandidate] = []
    for year in FRAME_YEARS:
        rows = parse_frame(frames_dir / f"frame_{year}.html", year)
        if len(rows) != EXPECTED_PER_FRAME:
            raise RuntimeError(
                f"frame_{year}.html: {len(rows)} candidates, expected {EXPECTED_PER_FRAME} — "
                "the frame changed since verification (data/frames/README.yaml); STOP"
            )
        bad_year = [r for r in rows if not r.date_issued.startswith(str(year))]
        if bad_year:
            raise RuntimeError(f"frame_{year}.html: rows outside {year}: {bad_year}")
        all_rows.extend(rows)
    ids = {r.publication_id for r in all_rows}
    if len(ids) != EXPECTED_PER_FRAME * len(FRAME_YEARS):
        raise RuntimeError(
            f"CBO frames: {len(ids)} distinct ids, expected 40 — duplicates across frames"
        )
    return all_rows


def write_candidates_csv(rows: list[CboCandidate], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow(asdict(r))


def read_candidates_csv(path: Path) -> list[CboCandidate]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return [
            CboCandidate(
                frame_year=int(r["frame_year"]),
                publication_id=r["publication_id"],
                page_url=r["page_url"],
                date_issued=r["date_issued"],
                type=r["type"],
                title=r["title"],
            )
            for r in csv.DictReader(fh)
        ]
