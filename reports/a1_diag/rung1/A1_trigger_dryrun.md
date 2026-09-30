# A1 - trigger dry-run (D-038 rung 1), no fix code

Trigger frozen at af06045 (`scripts/a1_diag/rung1/trigger.py`, sha256 9b1e7748bca534ab…), committed
before this run. Fires iff numeric-line count != TableFormer rows OR band count != TableFormer
columns, counted like-for-like (report choice C1). Reported, never acted on: the trigger is not
modified after this.

| family | tables | fired |
|---|---|---|
| MER held-out | 45 | 39 |
| ERP | 4 | 3 |
| STEO (oracle-covered) | 26 | 14 |
| tuning (3.6 sec3 p19, 4.2b sec4 p5) | 2 | 2 |
| BUDGET | 698 | 148 |
| CBO | 6 | 3 |
| MER uncovered | 1 | 0 |
| STEO uncovered (pp3-5 narrative) | 3 | 0 |
| other (AEO 1, CRPT 2) | 3 | 1 |
| **all** | **788** | **210** |

Per-table counts: `trigger_dryrun.json`. Fired list: `trigger_fired.json`,
sha256 c43737920c44c7c2bf7084e187dc6f8f6ce21ce63993afd22166698ea3180419. B5 asserts the same list.
