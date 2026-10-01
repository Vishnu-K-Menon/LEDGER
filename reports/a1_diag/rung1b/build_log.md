# Rung 1b build log (burned tables only; board.py appends one block per checkpoint)

### 2026-10-01T22:30:24Z B0: rung-1 emitter via the live path (no fix yet)

| family | cells | strict rung 1 -> 1b | header rung 1 -> 1b | fired before -> after | fell back |
|---|---|---|---|---|---|
| MER | 19761 | 89.33 -> **89.33** | 89.88 -> 89.88 | 41 -> 41 | 3 |
| ERP | 2764 | 92.51 -> **92.51** | 97.73 -> 97.73 | 3 -> 3 | 0 |
| STEO | 13046 | 95.76 -> **95.76** | 78.61 -> 78.61 | 14 -> 14 | 3 |

- newly fired (0): []
- no longer fired (0): []
- fired then fell back (6): ['MER 1.2 p5', 'MER 3.1 p3', 'MER 4.1 p3', 'STEO 4c p40', 'STEO 9a p52', 'STEO 10a p55']
- strict FELL vs rung 1 (0): []
- BUDGET/CBO pins on data/parsed_rung1b: identical=True changed=0 absent=[]
- clause-1 recall changed vs data/parsed: {'eia-pdf-sec3|10': '100.0 -> 99.55', 'eia-pdf-sec11|3': '100.0 -> 99.7'}

### 2026-10-01T22:32:42Z F1: flag + space + number in emitted cells

| family | cells | strict rung 1 -> 1b | header rung 1 -> 1b | fired before -> after | fell back |
|---|---|---|---|---|---|
| MER | 19761 | 89.33 -> **89.33** | 89.88 -> 89.88 | 41 -> 41 | 3 |
| ERP | 2764 | 92.51 -> **92.51** | 97.73 -> 97.73 | 3 -> 3 | 0 |
| STEO | 13046 | 95.76 -> **95.76** | 78.61 -> 78.61 | 14 -> 14 | 3 |

- newly fired (0): []
- no longer fired (0): []
- fired then fell back (6): ['MER 1.2 p5', 'MER 3.1 p3', 'MER 4.1 p3', 'STEO 4c p40', 'STEO 9a p52', 'STEO 10a p55']
- strict FELL vs rung 1 (0): []
- BUDGET/CBO pins on data/parsed_rung1b: identical=True changed=0 absent=[]
- clause-1 recall changed vs data/parsed: {'eia-pdf-sec3|10': '100.0 -> 99.78', 'eia-pdf-sec11|3': '100.0 -> 99.85'}

### 2026-10-01T22:36:59Z F1 (b): flag+number spacing in every emitted non-header cell (tokeniser-fused flags too)

| family | cells | strict rung 1 -> 1b | header rung 1 -> 1b | fired before -> after | fell back |
|---|---|---|---|---|---|
| MER | 19761 | 89.33 -> **89.33** | 89.88 -> 89.88 | 41 -> 41 | 3 |
| ERP | 2764 | 92.51 -> **92.51** | 97.73 -> 97.73 | 3 -> 3 | 0 |
| STEO | 13046 | 95.76 -> **95.76** | 78.61 -> 78.61 | 14 -> 14 | 3 |

- newly fired (0): []
- no longer fired (0): []
- fired then fell back (6): ['MER 1.2 p5', 'MER 3.1 p3', 'MER 4.1 p3', 'STEO 4c p40', 'STEO 9a p52', 'STEO 10a p55']
- strict FELL vs rung 1 (0): []
- BUDGET/CBO pins on data/parsed_rung1b: identical=True changed=0 absent=[]
- clause-1 recall changed vs data/parsed: none (unchanged on all 8)

### 2026-10-01T22:39:16Z F2: spanning TableFormer header kept when a page phrase with its words lies over a subset of its bands

| family | cells | strict rung 1 -> 1b | header rung 1 -> 1b | fired before -> after | fell back |
|---|---|---|---|---|---|
| MER | 19761 | 89.33 -> **89.33** | 89.88 -> 89.88 | 41 -> 41 | 3 |
| ERP | 2764 | 92.51 -> **92.51** | 97.73 -> 97.73 | 3 -> 3 | 0 |
| STEO | 13046 | 95.76 -> **95.76** | 78.61 -> 92.25 | 14 -> 14 | 3 |

- newly fired (0): []
- no longer fired (0): []
- fired then fell back (6): ['MER 1.2 p5', 'MER 3.1 p3', 'MER 4.1 p3', 'STEO 4c p40', 'STEO 9a p52', 'STEO 10a p55']
- strict FELL vs rung 1 (0): []
- BUDGET/CBO pins on data/parsed_rung1b: identical=True changed=0 absent=[]
- clause-1 recall changed vs data/parsed: none (unchanged on all 8)

### 2026-10-01T22:42:26Z F2 (tightened): spanning head must cross the midpoint of its span

| family | cells | strict rung 1 -> 1b | header rung 1 -> 1b | fired before -> after | fell back |
|---|---|---|---|---|---|
| MER | 19761 | 89.33 -> **89.33** | 89.88 -> 89.88 | 41 -> 41 | 3 |
| ERP | 2764 | 92.51 -> **92.51** | 97.73 -> 97.73 | 3 -> 3 | 0 |
| STEO | 13046 | 95.76 -> **95.76** | 78.61 -> 91.71 | 14 -> 14 | 3 |

- newly fired (0): []
- no longer fired (0): []
- fired then fell back (6): ['MER 1.2 p5', 'MER 3.1 p3', 'MER 4.1 p3', 'STEO 4c p40', 'STEO 9a p52', 'STEO 10a p55']
- strict FELL vs rung 1 (0): []
- BUDGET/CBO pins on data/parsed_rung1b: identical=True changed=0 absent=[]
- clause-1 recall changed vs data/parsed: none (unchanged on all 8)

### 2026-10-01T22:46:35Z F2 (as gap-tiled extents): a centred head takes the bands in its gap tile, in the check and the page cells

| family | cells | strict rung 1 -> 1b | header rung 1 -> 1b | fired before -> after | fell back |
|---|---|---|---|---|---|
| MER | 19761 | 89.33 -> **89.33** | 89.88 -> 91.44 | 41 -> 41 | 3 |
| ERP | 2764 | 92.51 -> **92.51** | 97.73 -> 97.73 | 3 -> 3 | 0 |
| STEO | 13046 | 95.76 -> **95.76** | 78.61 -> 97.59 | 14 -> 14 | 3 |

- newly fired (0): []
- no longer fired (0): []
- fired then fell back (6): ['MER 1.2 p5', 'MER 3.1 p3', 'MER 4.1 p3', 'STEO 4c p40', 'STEO 9a p52', 'STEO 10a p55']
- strict FELL vs rung 1 (0): []
- BUDGET/CBO pins on data/parsed_rung1b: identical=True changed=0 absent=[]
- clause-1 recall changed vs data/parsed: none (unchanged on all 8)

### 2026-10-01T22:51:19Z Trigger FN: live rule = merged TF body cell OR numeric lines != TF rows

| family | cells | strict rung 1 -> 1b | header rung 1 -> 1b | fired before -> after | fell back |
|---|---|---|---|---|---|
| MER | 19761 | 89.33 -> **91.55** | 89.88 -> 91.25 | 41 -> 46 | 3 |
| ERP | 2764 | 92.51 -> **100.0** | 97.73 -> 95.45 | 3 -> 4 | 0 |
| STEO | 13046 | 95.76 -> **96.57** | 78.61 -> 97.59 | 14 -> 11 | 2 |

- newly fired (7): ['MER 1.10 p23 (rebuilt)', 'MER 11.2 p5 (rebuilt)', 'MER 11.5 p8 (rebuilt)', 'MER 3.3e p12 (rebuilt)', 'MER 3.31 p13 (rebuilt)', 'ERP table22 sheet0 p1 (rebuilt)', 'STEO 7b p46 (rebuilt)']
- no longer fired (4): ['STEO 2 p32', 'STEO 3e p37', 'STEO 4c p40', 'STEO 5a p42']
- fired then fell back (5): ['MER 1.2 p5', 'MER 3.1 p3', 'MER 4.1 p3', 'STEO 9a p52', 'STEO 10a p55']
- strict FELL vs rung 1 (0): []
- BUDGET/CBO pins on data/parsed_rung1b: identical=True changed=0 absent=[]
- clause-1 recall changed vs data/parsed: none (unchanged on all 8)

### 2026-10-01T22:54:48Z Fallback cause: split numbers rejoined in cell text (safety >= 2 numbers)

| family | cells | strict rung 1 -> 1b | header rung 1 -> 1b | fired before -> after | fell back |
|---|---|---|---|---|---|
| MER | 19761 | 89.33 -> **94.74** | 89.88 -> 91.63 | 41 -> 46 | 0 |
| ERP | 2764 | 92.51 -> **100.0** | 97.73 -> 95.45 | 3 -> 4 | 0 |
| STEO | 13046 | 95.76 -> **96.57** | 78.61 -> 97.59 | 14 -> 11 | 2 |

- newly fired (7): ['MER 1.10 p23 (rebuilt)', 'MER 11.2 p5 (rebuilt)', 'MER 11.5 p8 (rebuilt)', 'MER 3.3e p12 (rebuilt)', 'MER 3.31 p13 (rebuilt)', 'ERP table22 sheet0 p1 (rebuilt)', 'STEO 7b p46 (rebuilt)']
- no longer fired (4): ['STEO 2 p32', 'STEO 3e p37', 'STEO 4c p40', 'STEO 5a p42']
- fired then fell back (2): ['STEO 9a p52', 'STEO 10a p55']
- strict FELL vs rung 1 (0): []
- BUDGET/CBO pins on data/parsed_rung1b: identical=True changed=0 absent=[]
- clause-1 recall changed vs data/parsed: none (unchanged on all 8)

### 2026-10-01T22:57:02Z Fallback cause: numbers inside an open parenthetical are label text (STEO 9a prose safety)

| family | cells | strict rung 1 -> 1b | header rung 1 -> 1b | fired before -> after | fell back |
|---|---|---|---|---|---|
| MER | 19761 | 89.33 -> **94.66** | 89.88 -> 91.63 | 41 -> 46 | 0 |
| ERP | 2764 | 92.51 -> **100.0** | 97.73 -> 95.45 | 3 -> 4 | 0 |
| STEO | 13046 | 95.76 -> **96.77** | 78.61 -> 97.59 | 14 -> 11 | 1 |

- newly fired (7): ['MER 1.10 p23 (rebuilt)', 'MER 11.2 p5 (rebuilt)', 'MER 11.5 p8 (rebuilt)', 'MER 3.3e p12 (rebuilt)', 'MER 3.31 p13 (rebuilt)', 'ERP table22 sheet0 p1 (rebuilt)', 'STEO 7b p46 (rebuilt)']
- no longer fired (4): ['STEO 2 p32', 'STEO 3e p37', 'STEO 4c p40', 'STEO 5a p42']
- fired then fell back (1): ['STEO 10a p55']
- strict FELL vs rung 1 (0): []
- BUDGET/CBO pins on data/parsed_rung1b: identical=True changed=0 absent=[]
- clause-1 recall changed vs data/parsed: none (unchanged on all 8)

### 2026-10-01T23:00:20Z Fallback cause (refined): a parenthetical must close on its line

| family | cells | strict rung 1 -> 1b | header rung 1 -> 1b | fired before -> after | fell back |
|---|---|---|---|---|---|
| MER | 19761 | 89.33 -> **94.74** | 89.88 -> 91.63 | 41 -> 46 | 0 |
| ERP | 2764 | 92.51 -> **100.0** | 97.73 -> 95.45 | 3 -> 4 | 0 |
| STEO | 13046 | 95.76 -> **96.77** | 78.61 -> 97.59 | 14 -> 11 | 1 |

- newly fired (7): ['MER 1.10 p23 (rebuilt)', 'MER 11.2 p5 (rebuilt)', 'MER 11.5 p8 (rebuilt)', 'MER 3.3e p12 (rebuilt)', 'MER 3.31 p13 (rebuilt)', 'ERP table22 sheet0 p1 (rebuilt)', 'STEO 7b p46 (rebuilt)']
- no longer fired (4): ['STEO 2 p32', 'STEO 3e p37', 'STEO 4c p40', 'STEO 5a p42']
- fired then fell back (1): ['STEO 10a p55']
- strict FELL vs rung 1 (0): []
- BUDGET/CBO pins on data/parsed_rung1b: identical=True changed=0 absent=[]
- clause-1 recall changed vs data/parsed: none (unchanged on all 8)

