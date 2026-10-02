"""Image-only page MEASURE (overnight 2026-10-01, Part 2): per page of a raw PDF, embedded-image
count and text-layer word count (``ledger.ingest.fetch.page_measures``). No threshold is applied
(``fetch.image_only_page_max_words`` is the owner's). Read-only.

    uv run python scripts/probe_image_pages.py <out.json>
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from ledger.config import load_config  # noqa: E402
from ledger.ingest.fetch import page_measures  # noqa: E402
from ledger.ingest.manifest import active_rows, read_manifest  # noqa: E402

PAGE_BY_PAGE = ["govinfo-BUDGET-2027-FCS", "govinfo-BUDGET-2026-CROSSCUT"]


def summary(ms) -> dict:
    img = [m for m in ms if m.images]
    return {
        "pages": len(ms),
        "pages_with_images": len(img),
        "pages_with_images_words": sorted(m.words for m in img if m.words is not None),
        "pages_zero_words": sum(1 for m in ms if m.words == 0),
        "pages_zero_words_no_images": sum(1 for m in ms if m.words == 0 and not m.images),
        "min_words_text_pages": min((m.words for m in ms if not m.images), default=None),
        "unreadable": sum(1 for m in ms if m.images is None or m.words is None),
    }


def main(out_path: str) -> int:
    cfg = load_config(REPO / "configs" / "base.yaml")
    _, rows = read_manifest(REPO / cfg.paths.manifest)
    parsed = REPO / cfg.paths.parsed_dir
    out: dict = {"sec7": None, "pilot": {}, "page_by_page": {}}
    sec7 = REPO / "data" / "raw_fresh" / "eia" / "eia-pdf-sec7.pdf"
    if sec7.exists():
        out["sec7"] = [asdict(m) for m in page_measures(sec7)]
    for r in active_rows(rows):
        if not (parsed / f"{r.unit_id}.json").exists():
            continue
        ms = page_measures(REPO / cfg.paths.raw_dir / r.source / f"{r.unit_id}.pdf")
        out["pilot"][r.unit_id] = summary(ms) | {"text_layer_ratio": r.text_layer_ratio}
        if r.unit_id in PAGE_BY_PAGE:
            out["page_by_page"][r.unit_id] = [asdict(m) for m in ms]
    Path(out_path).write_text(json.dumps(out, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
