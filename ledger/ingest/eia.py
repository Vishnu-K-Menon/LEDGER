"""EIA listing (D-034). The sitemap is a flat list of HTML landing pages and lists no PDFs
(checked 2026-09-20), so the frame actually used is: sitemap -> the configured landing pages ->
PDF links found on them. Latest edition only; robots Disallow patterns are respected."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin

from ledger.config import FetchConfig
from ledger.ingest.http import Fetcher

HREF_PDF = re.compile(r"""href=["']([^"']+\.pdf)["']""", re.IGNORECASE)
MER_SECTION = re.compile(r"/pdf/sec(\d+)\.pdf$")
LOC = re.compile(r"<loc>([^<]+)</loc>")


@dataclass(frozen=True)
class EiaUnit:
    series: str  # mer | steo | aeo
    url: str
    title: str
    section: int | None = None


def sitemap_lists(fetcher: Fetcher, cfg: FetchConfig) -> dict[str, bool]:
    """Does the sitemap list each configured landing page? Also returns pdf_count / is_index."""
    xml = fetcher.get_text(cfg.eia_sitemap_url, source="eia")
    locs = LOC.findall(xml)
    out = {
        name: any(loc.rstrip("/") == url.rstrip("/") for loc in locs)
        for name, url in cfg.eia_landing_pages.items()
    }
    out["_is_index"] = "<sitemapindex" in xml
    out["_pdf_count"] = sum(1 for loc in locs if loc.lower().endswith(".pdf"))
    out["_url_count"] = len(locs)
    return out


def _disallowed(url: str, cfg: FetchConfig) -> bool:
    return any(p in url for p in cfg.eia_disallow_patterns)


def list_units(fetcher: Fetcher, cfg: FetchConfig) -> list[EiaUnit]:
    units: list[EiaUnit] = []
    for series, page in cfg.eia_landing_pages.items():
        html = fetcher.get_text(page, source="eia")
        seen: set[str] = set()
        for href in HREF_PDF.findall(html):
            url = urljoin(page, href)
            if url in seen or _disallowed(url, cfg):
                continue
            seen.add(url)
            if series == "mer":
                m = MER_SECTION.search(url)
                if m:
                    units.append(
                        EiaUnit(
                            "mer",
                            url,
                            f"Monthly Energy Review — section {m.group(1)}",
                            int(m.group(1)),
                        )
                    )
            elif series == "steo" and url.endswith("steo_full.pdf"):
                units.append(EiaUnit("steo", url, "Short-Term Energy Outlook — full report"))
            elif series == "aeo" and url.endswith("AEO_Narrative.pdf"):
                units.append(EiaUnit("aeo", url, "Annual Energy Outlook — narrative"))
    # de-duplicate, stable order
    uniq: dict[str, EiaUnit] = {}
    for u in units:
        uniq.setdefault(u.url, u)
    return sorted(uniq.values(), key=lambda u: (u.series, u.section or 0, u.url))
