# A2 - header-association misses of the current parse, classified

All misses: 79 (MER held-out 72, MER tuning 4, ERP 3).

| family | dropped column | garbled / fused | body-caused |
|---|---|---|---|
| MER held-out | 20 | 29 | 23 |
| MER tuning | 1 | 0 | 3 |
| ERP | 1 | 0 | 2 |
| **all** | 22 | 29 | 28 |

Garbled / fused with an EMPTY parsed header: 2.

**Rule (on the MER held-out misses, n = 72):** dropped 20 (28%), garbled 29 (40%), body-caused 23 (32%) -> **TableFormer headers**. On all 79 misses: dropped 28%, garbled 37%.
