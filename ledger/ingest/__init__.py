"""Corpus acquisition (T2, D-034) and parse + chunk (T3, D-032).

Stages of ``ledger ingest``: ``list`` (frames -> candidates -> granule gate -> seeded draw ->
manifest rows; downloads nothing), ``fetch`` (requires ``--draw-confirmed``; hashes, page counts,
text-layer ratio), ``parse`` (T3; the D-001 ``--all/--confirmed`` stop applies here).
"""
