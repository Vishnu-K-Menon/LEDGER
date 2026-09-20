"""GovInfo listing (D-034): ``/published`` by dateIssued, package and granule summaries, the
granule reliability gate, and the CRPT cost-estimate filter.

NEVER ``/collections/{code}/{date}`` — it filters ``lastModified`` (that is why GAOREPORTS
looked current and is not). Nothing here downloads a PDF; the gate reads ``txtLink``
renditions (served as ``/htm``), which are text, to judge self-containment.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from ledger.config import FetchConfig
from ledger.ingest.http import Fetcher

log = logging.getLogger(__name__)

# Granule classes that are never content units (front matter, contents) — excluded from draws
# and recorded as such in the manifest header notes.
NON_CONTENT_CLASSES = frozenset({"FRONTMATTER", "TOC", "BACKMATTER"})

UNIT_PHRASES = re.compile(
    r"(in (?:millions|billions|thousands) of (?:\d{4} )?(?:chained (?:\(\d{4}\) )?)?dollars"
    r"|millions of dollars|billions of dollars|thousands of dollars"
    r"|chained \(?\d{4}\)? dollars|percent(?:age)? (?:change|of)|per ?cent"
    r"|fiscal years?|calendar years?|by fiscal year|\bFY ?\d{2,4}\b)",
    re.IGNORECASE,
)
NUMERIC_ROW = re.compile(
    r"^\s*\S.{0,80}?(?:[-–]?\$?\d[\d,]*\.?\d*\s+){2,}[-–]?\$?\d[\d,]*\.?\d*\s*$"
)
TABLE_HEADING = re.compile(r"^\s*table\s+[A-Z]?[-\d.]+", re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(s: str) -> str:
    s = re.sub(r"(?is)<(script|style).*?</\1>", " ", s)
    s = TAG_RE.sub("\n", s)
    return re.sub(r"\n{2,}", "\n", s)


@dataclass
class Package:
    package_id: str
    title: str
    date_issued: str
    doc_class: str
    pages: int | None = None
    pdf_link: str | None = None
    txt_link: str | None = None
    granule_count: int | None = None


@dataclass
class Granule:
    package_id: str
    granule_id: str
    title: str
    granule_class: str
    date_issued: str
    pdf_link: str | None = None
    txt_link: str | None = None
    pages: int | None = None


CheckResult = Literal["pass", "fail", "field-absent", "flag", "n/a"]


@dataclass
class GateReport:
    source: str
    packages_checked: list[str] = field(default_factory=list)
    granule_total: int = 0
    check1_pdflink: CheckResult = "n/a"
    check1_pages: CheckResult = "n/a"
    check2_self_contained: CheckResult = "n/a"
    check3_boundary: CheckResult = "n/a"
    unit_kind: Literal["granule", "report"] = "report"
    details: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        # `field-absent` on pages and `flag` on the boundary heuristic are not failures (D-034,
        # owner's amendment): a source can lack `pages` and still be self-contained.
        return "fail" not in (self.check1_pdflink, self.check2_self_contained, self.check3_boundary)


class GovInfo:
    def __init__(self, fetcher: Fetcher, cfg: FetchConfig, api_key: str) -> None:
        self.f = fetcher
        self.cfg = cfg
        self.key = api_key
        self.base = cfg.govinfo_base_url.rstrip("/")

    # ---- endpoints --------------------------------------------------------------------------

    def _get(self, path_or_url: str, **params: Any) -> Any:
        url = path_or_url if path_or_url.startswith("http") else f"{self.base}{path_or_url}"
        params["api_key"] = self.key
        return self.f.get_json(url, source="govinfo", params=params)

    def published(
        self, collection: str, start: str, end: str, *, limit: int | None = None
    ) -> list[Package]:
        """All packages with dateIssued in [start, end] for one collection (cursor-paged)."""
        out: list[Package] = []
        data = self._get(
            f"/published/{start}/{end}",
            collection=collection,
            pageSize=self.cfg.govinfo_page_size,
            offsetMark="*",
        )
        while True:
            for p in data.get("packages", []):
                out.append(
                    Package(
                        package_id=p["packageId"],
                        title=p.get("title", ""),
                        date_issued=p.get("dateIssued", ""),
                        doc_class=p.get("docClass", ""),
                    )
                )
                if limit and len(out) >= limit:
                    return out
            nxt = data.get("nextPage")
            if not nxt:
                return out
            data = self._get(nxt)

    def package_summary(self, pkg: Package) -> Package:
        s = self._get(f"/packages/{pkg.package_id}/summary")
        pages = s.get("pages")
        pkg.pages = int(pages) if pages not in (None, "") else None
        dl = s.get("download", {}) or {}
        pkg.pdf_link = dl.get("pdfLink")
        pkg.txt_link = dl.get("txtLink")
        pkg.title = s.get("title", pkg.title)
        return pkg

    def granules(self, pkg: Package) -> list[Granule]:
        out: list[Granule] = []
        data = self._get(
            f"/packages/{pkg.package_id}/granules",
            pageSize=self.cfg.govinfo_page_size,
            offsetMark="*",
        )
        pkg.granule_count = int(data.get("count", 0) or 0)
        while True:
            for g in data.get("granules", []):
                out.append(
                    Granule(
                        package_id=pkg.package_id,
                        granule_id=g["granuleId"],
                        title=g.get("title", ""),
                        granule_class=g.get("granuleClass", ""),
                        date_issued=g.get("dateIssued", pkg.date_issued),
                    )
                )
            nxt = data.get("nextPage")
            if not nxt:
                return out
            data = self._get(nxt)

    def granule_summary(self, g: Granule) -> Granule:
        s = self._get(f"/packages/{g.package_id}/granules/{g.granule_id}/summary")
        dl = s.get("download", {}) or {}
        g.pdf_link = dl.get("pdfLink")
        g.txt_link = dl.get("txtLink")
        pages = s.get("pages")
        g.pages = int(pages) if pages not in (None, "") else None
        return g

    def text_of(self, link: str | None) -> str:
        if not link:
            return ""
        return _strip_html(self.f.get_text(link, source="govinfo", params={"api_key": self.key}))

    # ---- helpers ----------------------------------------------------------------------------

    @staticmethod
    def series_key(p: Package) -> str:
        """Recurring-series key: ``BUDGET-2027-APP`` -> ``BUDGET-APP``, ``ERP-2026`` -> ``ERP``.
        Titles are not stable across editions ("Appendix" vs "Technical Supplement to the 2026
        Budget: Appendix"), package ids are. Falls back to a year-stripped title."""
        m = re.match(r"^([A-Z]+)-\d{4}(?:-([A-Za-z]+))?", p.package_id)
        if m:
            return m.group(1) + (f"-{m.group(2)}" if m.group(2) else "")
        return re.sub(r"(?:fy ?)?(?:19|20)\d{2}|\s+", " ", p.title.lower()).strip()

    @classmethod
    def latest_per_series(cls, packages: list[Package]) -> list[Package]:
        """One edition per recurring series (D-034): keep the newest dateIssued per series key."""
        best: dict[str, Package] = {}
        for p in packages:
            k = cls.series_key(p)
            if k not in best or p.date_issued > best[k].date_issued:
                best[k] = p
        return sorted(best.values(), key=lambda p: p.package_id)

    # ---- the granule reliability gate (D-034) ------------------------------------------------

    def gate(
        self, source: str, packages: list[Package], granules: dict[str, list[Granule]]
    ) -> GateReport:
        rep = GateReport(source=source)
        content = [
            g
            for pid in sorted(granules)
            for g in granules[pid]
            if g.granule_class not in NON_CONTENT_CLASSES
        ]
        rep.packages_checked = sorted(granules)
        rep.granule_total = sum(len(v) for v in granules.values())
        if not content:
            rep.details.append("no granules on any package -> report-level by construction")
            rep.unit_kind = "report"
            return rep

        # Check 1: every granule carries its own pdfLink AND pages in metadata.
        for g in content:
            if g.pdf_link is None:
                self.granule_summary(g)
        no_pdf = [g.granule_id for g in content if not g.pdf_link]
        rep.check1_pdflink = "fail" if no_pdf else "pass"
        if no_pdf:
            rep.details.append(f"granules without pdfLink: {no_pdf[:5]}")
        if all(g.pages is None for g in content):
            rep.check1_pages = "field-absent"
            rep.details.append(
                "granule summaries carry no `pages`; fallback = package pages / granule count "
                "(pages_source: estimated) until --stage fetch measures the file"
            )
        elif any(g.pages is None for g in content):
            rep.check1_pages = "flag"
        else:
            rep.check1_pages = "pass"

        # Check 2: spot-check N granules (tables first) for their own table headers + unit/period
        # statement. A txtLink rendition shorter than gate_min_text_chars is a stub (ERP table
        # granules serve ~465 bytes): the check cannot be judged from metadata and is FLAGGED —
        # self-containment is then verified on the fetched PDF before parse, not assumed.
        tables = [g for g in content if g.granule_class.upper() == "TABLE"] or content
        n = min(self.cfg.gate_spot_check_n, len(tables))
        idx = [round(i * (len(tables) - 1) / max(n - 1, 1)) for i in range(n)]
        sample = [tables[i] for i in sorted(set(idx))]
        fails, stubs, texts = [], [], {}
        for g in sample:
            if g.txt_link is None:
                self.granule_summary(g)
            t = self.text_of(g.txt_link)
            texts[g.granule_id] = t
            if len(t.strip()) < self.cfg.gate_min_text_chars:
                stubs.append(g.granule_id)
                rep.details.append(
                    f"{g.granule_id}: txtLink rendition "
                    f"{'absent' if not g.txt_link else 'is a stub'} "
                    f"({len(t.strip())} chars) -> unjudgeable from metadata"
                )
                continue
            rows = sum(1 for ln in t.splitlines() if NUMERIC_ROW.match(ln))
            units = UNIT_PHRASES.findall(t)
            if rows >= 3 and not units:
                fails.append(g.granule_id)
                rep.details.append(f"{g.granule_id}: {rows} numeric rows, no unit/period phrase")
            else:
                rep.details.append(
                    f"{g.granule_id}: {rows} numeric rows; unit phrases "
                    f"{sorted({u.lower() for u in units})[:4]}"
                )
        if fails:
            rep.check2_self_contained = "fail"
        elif len(stubs) == len(sample):
            rep.check2_self_contained = "field-absent"
        elif stubs:
            rep.check2_self_contained = "flag"
        else:
            rep.check2_self_contained = "pass"

        # Check 3: no table spans a granule boundary (heuristic, flagged for the owner).
        flags = []
        for g in sample:
            pid_gr = granules[g.package_id]
            i = next((k for k, x in enumerate(pid_gr) if x.granule_id == g.granule_id), None)
            if i is None or i + 1 >= len(pid_gr):
                continue
            nxt = pid_gr[i + 1]
            if nxt.pdf_link is None:
                self.granule_summary(nxt)
            t_a = texts.get(g.granule_id) or self.text_of(g.txt_link)
            t_b = self.text_of(nxt.txt_link)
            if min(len(t_a.strip()), len(t_b.strip())) < self.cfg.gate_min_text_chars:
                continue  # stub renditions: nothing to judge
            tail = [ln for ln in t_a.splitlines() if ln.strip()][-15:]
            head = [ln for ln in t_b.splitlines() if ln.strip()][:15]
            tail_num = sum(1 for ln in tail if NUMERIC_ROW.match(ln))
            head_num = sum(1 for ln in head if NUMERIC_ROW.match(ln))
            head_has_heading = any(TABLE_HEADING.match(ln) for ln in head)
            if tail_num >= 5 and head_num >= 5 and not head_has_heading:
                flags.append(f"{g.granule_id} -> {nxt.granule_id}")
        judged = any(
            len(texts.get(g.granule_id, "").strip()) >= self.cfg.gate_min_text_chars for g in sample
        )
        rep.check3_boundary = "flag" if flags else ("pass" if judged else "field-absent")
        if flags:
            rep.details.append(f"possible table across boundary (eyeball): {flags}")
        rep.unit_kind = "granule" if rep.passed else "report"
        return rep

    # ---- CRPT: only committee reports that embed a CBO cost estimate ----------------------------

    def crpt_filter(self, sample: list[Package]) -> tuple[list[Package], int]:
        terms = self.cfg.crpt_filter_terms
        passed: list[Package] = []
        for p in sample:
            self.package_summary(p)
            text = self.text_of(p.txt_link)
            if not text:
                gs = self.granules(p)
                if gs:
                    self.granule_summary(gs[0])
                    text = self.text_of(gs[0].txt_link)
            low = text.lower()
            if all(t.lower() in low for t in terms.all_of) and any(
                t.lower() in low for t in terms.any_of
            ):
                passed.append(p)
        return passed, len(sample)
