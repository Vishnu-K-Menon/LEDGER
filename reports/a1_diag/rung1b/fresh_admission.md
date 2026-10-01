# D-039 - fresh MER / ERP admission (counts only)

From the fresh parse only TableItem page + bbox (stub documents); the unchanged `oracle.py` (A6) and `f5_sizing.py` (clause (b)) run on a sha256-verified mirror tree. MER: A6 then clause (b); a page with no TableItem uses the page text area and every admitted cell there is a miss by rule. ERP: A6 against the granule xls.

MER matched tables: 39 (fresh set). Matched pages: 45. Pages with no detected TableItem (page-text-area region, ruling 3): 6 ['eia-pdf-sec2 p22 (2.5)', 'eia-pdf-sec6 p9 (6.2)', 'eia-pdf-sec6 p10 (6.3)', 'eia-pdf-sec9 p18 (9.1)', 'eia-pdf-sec10 p20 (10.4a)', 'eia-pdf-sec10 p22 (10.4c)'].

**Ruling 3 applies to 0 tables** []: every other matched table has a detected TableItem on its table page. The 6 page(s) above are Sources-notes pages whose top-quarter line is 'Table X.Y Sources' for an id already matched on its table page (the scan carries the first page's export match to a repeated id); each contributes 0 oracle cells. Reported, not changed (a further scan change is the owner's).

| section | matched tables | TableItems admitted | undetected regions | oracle cells | A6-admitted | on the line | flag only | not on the line | row not found | admitted after (b) | miss by rule | numeric-but-different | share of A6 | tripwire (> 1 %) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| sec2 | 9 | 10 | 1 | 5385 | 4855 | 4836 | 14 | 5 | 0 | 4850 | 0 | 3 | 0.06% | ok |
| sec5 | 1 | 1 | 0 | 256 | 256 | 256 | 0 | 0 | 0 | 256 | 0 | 0 | 0.00% | ok |
| sec6 | 3 | 5 | 2 | 1276 | 1229 | 1227 | 0 | 2 | 0 | 1227 | 0 | 0 | 0.00% | ok |
| sec7 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.00% | ok |
| sec9 | 10 | 11 | 1 | 1605 | 1573 | 1571 | 1 | 1 | 0 | 1572 | 0 | 0 | 0.00% | ok |
| sec10 | 10 | 12 | 2 | 4965 | 4618 | 4547 | 56 | 15 | 0 | 4603 | 0 | 7 | 0.15% | ok |
| sec12 | 6 | 6 | 0 | 3379 | 1225 | 1208 | 15 | 2 | 0 | 1223 | 0 | 2 | 0.16% | ok |

Clause-(b) exclusions by band class (all sections): numeric-but-different 12, other non-numeric 11, split-token, joined == value 2.

## ERP (A6, granule xls)

8 granules · 8 sheet/TableItem pairs · oracle cells 5017 · A6-admitted 5017 (100.0%).

| granule | page | oracle cells | A6-admitted | note |
|---|---|---|---|---|
| ERP-2026-table33 sheet0 | 1 | 0 | 0 | column count: oracle 17 vs printed 14 |
| ERP-2026-table43 sheet0 | 1 | 804 | 804 |  |
| ERP-2026-table52 sheet0 | 1 | 713 | 713 |  |
| ERP-2026-table7 sheet0 | 1 | 737 | 737 |  |
| ERP-2026-table28 sheet0 | 1 | 897 | 897 |  |
| ERP-2026-table10 sheet0 | 1 | 871 | 871 |  |
| ERP-2026-table14 sheet0 | 1 | 995 | 995 |  |
| ERP-2026-table59 sheet0 | 1 | 0 | 0 | column count: oracle 0 vs printed 9 |

**Tripwire:** not hit in any section.

