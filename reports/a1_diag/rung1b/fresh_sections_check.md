# Fresh MER sections 7 and 12 (and burned sec13): page-level facts

Fact-finding only (owner, 2026-09-30): no fix, no decision, no admission change. The PDFs are read programmatically (geometry, images, lines naming a table: ids and titles only, no body numbers). The fresh parse is not opened. Export check = `xls.php?tbl=` through the project Fetcher (https), file type and the export's own title only.

## sec7 (fresh, data/raw_fresh/eia/eia-pdf-sec7.pdf, 32 pages)
## Per section

### sec7 (fresh; D-039 'entire')

- Pages: 32, all /Rotate 0, 612x792 portrait. Figure (chart) pages with a text layer: [2, 4, 8, 12, 16, 18]. **Image-only pages** (running header, about 12 words, plus 5-6 images of about 11-13 % of the page each, no body text layer): [3, 5, 6, 7, 9, 10, 11, 13, 14, 15, 17, 19, 20, 21, 22, 23, 24, 25, 26, 27] (20 pages). Sources-notes pages: [28, 29, 30, 31]; p32 continues the notes.
- (a) Printed tables: the ids named in the text layer are only those in the Sources notes (7.1, 7.2b, 7.2c, 7.3b, 7.4b, 7.6, 7.7b). The section's per-table exports exist (title names the table) for: 7.1, 7.2b, 7.2c, 7.3b, 7.4b, 7.6, 7.7b, 7.2a, 7.3a, 7.3c, 7.4a, 7.4c, 7.5, 7.7a, 7.7c; not found: none. The tables sit in the image-only pages (they follow each Figure page in the section's order); their ids are INFERRED from that order and the export list, not read - no table id or title is in the text layer, and the pages were not viewed (viewing would expose values).
- Count: 15 table ids with an export against 20 image-only pages, so some tables take more than one page (inferred; the page-to-table mapping is not read).
- (b) Why `page_ids` missed them: the tables are printed as images - there is no text layer to read an id from (not position, not rotation). Docling found 0 tables here for the same reason (OCR is off, D2). The one id `page_ids` did find (7.6, p31) is the notes line 'Table 7.6 Sources' at y 0.02, not a table heading - so item 2's '7.6 excluded: title check failed' was a notes line; table 7.6 itself is image-only.
- (c) Exports: see the table below (type and export title only).
- Charts / notes rather than tables: the Figure pages are charts; p28-32 are Sources notes; the image-only pages are the table positions (content not verified).

### sec12 (fresh; D-039 'entire'; Appendices A-F)

- Pages: 40, all /Rotate 0, 612x792 portrait. Text tables headed with LETTER ids (page, id, y): [(2, 'A1', 0.4), (19, 'B1', 0.02), (20, 'B2', 0.02), (20, 'B3', 0.36), (22, 'C1', 0.07), (24, 'D1', 0.1), (30, 'E1', 0.02), (31, 'E2', 0.02), (32, 'E3', 0.02), (33, 'E4', 0.02), (36, 'F1', 0.02)]. Image-only pages: [3, 4, 5, 6, 7] (one image of 63-75 % of the page each) in Appendix A (bookmark MER_A; 'Table A6 Sources' on p15).
- (a) Printed tables: A1, A2, A3, A4, A5, A6, B1, B2, B3, C1, D1, E1, E2, E3, E4, F1 (16); A2-A6 are on the image-only pages (ids INFERRED from the Appendix A bookmarks, the Sources note and the export titles; not read). Exports whose title names the table: A2, A3, A4, A5, A6, C1, E1, E2, E3, E4, F1; workbook returned without a matching title (treated as not found): A1, B1, B2, B3, D1.
- (b) Why `page_ids` missed them: FORMAT - `orc.TABLE_ID` requires `digits.digits` (e.g. 12.1); appendix tables are 'Table B1.', 'Table E1.' etc. `page_ids` tests every top-quarter line (`fresh_oracle.py:81-86`), so C1 and D1 (y 0.07 / 0.10) were missed for the id format alone (corrected, owner, D-039 status 2026-09-30); A2-A6 are images. Not rotation.
- (c) Exports: see below. Zero-padded tbl forms (TA01 ...) return untitled workbooks.

### sec13 (burned pilot)

- 22 pages, all /Rotate 0, 612x792 portrait: the Glossary - prose on every page, no line anywhere naming a table (digit or letter id, or a Sources note), no images, no bookmarks. **sec13 has no tables**; Docling's 0 is correct.


| page | /Rotate | w x h | orientation | chars | upright | words | images (page share) | lines naming a table (y, kind: text) | first line | page class |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 0 | 612x792 | portrait | 30 | 1.0 | 2 | - | - | Electricity | divider / blank |
| 2 | 0 | 612x792 | portrait | 1057 | 1.0 | 192 | - | - | Figure Electricity Overview | figure (chart) page |
| 3 | 0 | 612x792 | portrait | 87 | 1.0 | 12 | [0.12, 0.12, 0.12, 0.12, 0.12, 0.12] | - | U. S. Energy Information Administration / Monthly Energy Rev | image-only (header + images; no body text) |
| 4 | 0 | 612x792 | portrait | 1317 | 1.0 | 232 | - | - | Figure Electricity Net Generation | figure (chart) page |
| 5 | 0 | 612x792 | portrait | 87 | 1.0 | 12 | [0.12, 0.12, 0.12, 0.12, 0.12, 0.12] | - | U. S. Energy Information Administration / Monthly Energy Rev | image-only (header + images; no body text) |
| 6 | 0 | 612x792 | portrait | 86 | 1.0 | 12 | [0.13, 0.13, 0.13, 0.13, 0.13, 0.13] | - | U. S. Energy Information Administration / Monthly Energy Rev | image-only (header + images; no body text) |
| 7 | 0 | 612x792 | portrait | 87 | 1.0 | 12 | [0.12, 0.12, 0.12, 0.12, 0.12, 0.12] | - | U. S. Energy Information Administration / Monthly Energy Rev | image-only (header + images; no body text) |
| 8 | 0 | 612x792 | portrait | 1307 | 0.93 | 206 | - | - | Figure Consumption of Selected Combustible Fuels for Electri | figure (chart) page |
| 9 | 0 | 612x792 | portrait | 86 | 1.0 | 12 | [0.12, 0.12, 0.12, 0.12, 0.12, 0.12] | - | U. S. Energy Information Administration / Monthly Energy Rev | image-only (header + images; no body text) |
| 10 | 0 | 612x792 | portrait | 85 | 1.0 | 12 | [0.13, 0.13, 0.13, 0.13, 0.13, 0.13] | - | U. S. Energy Information Administration / Monthly Energy Rev | image-only (header + images; no body text) |
| 11 | 0 | 612x792 | portrait | 87 | 1.0 | 12 | [0.12, 0.12, 0.12, 0.12, 0.12, 0.12] | - | U. S. Energy Information Administration / Monthly Energy Rev | image-only (header + images; no body text) |
| 12 | 0 | 612x792 | portrait | 1346 | 0.93 | 209 | - | - | Figure Consumption of Selected Combustible Fuels for Electri | figure (chart) page |
| 13 | 0 | 612x792 | portrait | 87 | 1.0 | 12 | [0.12, 0.12, 0.12, 0.12, 0.12, 0.12] | - | U. S. Energy Information Administration / Monthly Energy Rev | image-only (header + images; no body text) |
| 14 | 0 | 612x792 | portrait | 85 | 1.0 | 12 | [0.13, 0.13, 0.13, 0.13, 0.13, 0.13] | - | U. S. Energy Information Administration / Monthly Energy Rev | image-only (header + images; no body text) |
| 15 | 0 | 612x792 | portrait | 86 | 1.0 | 12 | [0.12, 0.12, 0.12, 0.12, 0.12, 0.12] | - | U. S. Energy Information Administration / Monthly Energy Rev | image-only (header + images; no body text) |
| 16 | 0 | 612x792 | portrait | 667 | 0.9 | 137 | - | - | Figure Stocks of Coal and Petroleum: Electric Power Sector | figure (chart) page |
| 17 | 0 | 612x792 | portrait | 87 | 1.0 | 12 | [0.11, 0.11, 0.11, 0.11, 0.11, 0.11] | - | U. S. Energy Information Administration / Monthly Energy Rev | image-only (header + images; no body text) |
| 18 | 0 | 612x792 | portrait | 1369 | 1.0 | 232 | - | - | Figure Electricity End Use | figure (chart) page |
| 19 | 0 | 612x792 | portrait | 88 | 1.0 | 12 | [0.11, 0.11, 0.11, 0.11, 0.11, 0.11] | - | U. S. Energy Information Administration / Monthly Energy Rev | image-only (header + images; no body text) |
| 20 | 0 | 612x792 | portrait | 87 | 1.0 | 12 | [0.11, 0.11, 0.11, 0.11, 0.11, 0.11] | - | U. S. Energy Information Administration / Monthly Energy Rev | image-only (header + images; no body text) |
| 21 | 0 | 612x792 | portrait | 88 | 1.0 | 12 | [0.11, 0.11, 0.11, 0.11, 0.11, 0.11] | - | U. S. Energy Information Administration / Monthly Energy Rev | image-only (header + images; no body text) |
| 22 | 0 | 612x792 | portrait | 87 | 1.0 | 12 | [0.13, 0.13, 0.13, 0.13, 0.13] | - | U. S. Energy Information Administration / Monthly Energy Rev | image-only (header + images; no body text) |
| 23 | 0 | 612x792 | portrait | 88 | 1.0 | 12 | [0.13, 0.13, 0.13, 0.13, 0.13] | - | U. S. Energy Information Administration / Monthly Energy Rev | image-only (header + images; no body text) |
| 24 | 0 | 612x792 | portrait | 88 | 1.0 | 12 | [0.11, 0.11, 0.11, 0.11, 0.11, 0.11] | - | U. S. Energy Information Administration / Monthly Energy Rev | image-only (header + images; no body text) |
| 25 | 0 | 612x792 | portrait | 86 | 1.0 | 12 | [0.11, 0.11, 0.11, 0.11, 0.11, 0.11] | - | U. S. Energy Information Administration / Monthly Energy Rev | image-only (header + images; no body text) |
| 26 | 0 | 612x792 | portrait | 85 | 1.0 | 12 | [0.11, 0.11, 0.11, 0.11, 0.11, 0.11] | - | U. S. Energy Information Administration / Monthly Energy Rev | image-only (header + images; no body text) |
| 27 | 0 | 612x792 | portrait | 85 | 1.0 | 12 | [0.11, 0.11, 0.11, 0.11, 0.11, 0.11] | - | U. S. Energy Information Administration / Monthly Energy Rev | image-only (header + images; no body text) |
| 28 | 0 | 612x792 | portrait | 4104 | 1.0 | 561 | - | 0.77, Sources note: Table 7.1 Sources | Electricity | notes (Sources) |
| 29 | 0 | 612x792 | portrait | 2744 | 1.0 | 358 | - | 0.51, Sources note: Table 7.2b Sources; 0.82, Sources note: Table 7.2c Sources | October Unpublished Economic Regulatory Administration (ERA) | notes (Sources) |
| 30 | 0 | 612x792 | portrait | 2618 | 1.0 | 343 | - | 0.33, Sources note: Table 7.3b Sources; 0.63, Sources note: Table 7.4b Sources | October Federal Energy Regulatory Commission (FERC), Form "M | notes (Sources) |
| 31 | 0 | 612x792 | portrait | 2204 | 1.0 | 283 | - | 0.02, Sources note: Table 7.6 Sources; 0.77, Sources note: Table 7.7b Sources | Table 7.6 Sources | notes (Sources) |
| 32 | 0 | 612x792 | portrait | 565 | 1.0 | 71 | - | - | EIA, Form "Annual Electric Generator Report," and Form "Annu | text (no table heading) |

Bookmarks: 0

## sec12 (fresh, data/raw_fresh/eia/eia-pdf-sec12.pdf, 40 pages)

| page | /Rotate | w x h | orientation | chars | upright | words | images (page share) | lines naming a table (y, kind: text) | first line | page class |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 0 | 612x792 | portrait | 71 | 1.0 | 7 | - | - | Appendix A | divider / blank |
| 2 | 0 | 612x792 | portrait | 4088 | 1.0 | 625 | - | 0.4, letter id: Table A1. Approximate Heat Content of Petroleum and Biofuels | British Thermal Unit Conversion Factors | text table (headed) |
| 3 | 0 | 612x792 | portrait | 84 | 1.0 | 12 | [0.69] | - | U. S. Energy Information Administration / Monthly Energy Rev | image-only (header + images; no body text) |
| 4 | 0 | 612x792 | portrait | 83 | 1.0 | 12 | [0.7] | - | U. S. Energy Information Administration / Monthly Energy Rev | image-only (header + images; no body text) |
| 5 | 0 | 612x792 | portrait | 84 | 1.0 | 12 | [0.63] | - | U. S. Energy Information Administration / Monthly Energy Rev | image-only (header + images; no body text) |
| 6 | 0 | 612x792 | portrait | 83 | 1.0 | 12 | [0.75] | - | U. S. Energy Information Administration / Monthly Energy Rev | image-only (header + images; no body text) |
| 7 | 0 | 612x792 | portrait | 86 | 1.0 | 12 | [0.7] | - | U. S. Energy Information Administration / Monthly Energy Rev | image-only (header + images; no body text) |
| 8 | 0 | 612x792 | portrait | 4910 | 1.0 | 759 | - | - | Thermal Conversion Factor Source Documentation | text (no table heading) |
| 9 | 0 | 612x792 | portrait | 5243 | 1.0 | 778 | - | - | Ethane. EIA estimated the thermal conversion factor to be mi | text (no table heading) |
| 10 | 0 | 612x792 | portrait | 5293 | 1.0 | 790 | - | - | blendstock is million Btu per barrel in and million Btu per  | text (no table heading) |
| 11 | 0 | 612x792 | portrait | 4983 | 1.0 | 695 | - | - | Petroleum Coke, Marketable. EIA adopted the thermal conversi | text (no table heading) |
| 12 | 0 | 612x792 | portrait | 4726 | 1.0 | 737 | - | - | Residual Fuel Oil. EIA adopted the thermal conversion factor | text (no table heading) |
| 13 | 0 | 612x792 | portrait | 4556 | 1.0 | 702 | - | - | Department of Agriculture: in in in and from University of I | text (no table heading) |
| 14 | 0 | 612x792 | portrait | 5618 | 1.0 | 806 | - | - | Coal Consumption, Electric Power Sector. Calculated annually | text (no table heading) |
| 15 | 0 | 612x792 | portrait | 5483 | 1.0 | 770 | - | 0.22, Sources note: Table A6 Sources | of Industrial, Commercial, and Institutional Coal Users” (fo | notes (Sources) |
| 16 | 0 | 612x792 | portrait | 48 | 1.0 | 5 | - | - | THIS PAGE INTENTIONALLY LEFT BLANK | divider / blank |
| 17 | 0 | 612x792 | portrait | 112 | 1.0 | 12 | - | - | Appendix B | divider / blank |
| 18 | 0 | 612x792 | portrait | 1363 | 1.0 | 210 | - | - | Metric Conversion Factors, Metric Prefixes, and Other Physic | text (no table heading) |
| 19 | 0 | 612x792 | portrait | 2811 | 1.0 | 440 | - | 0.02, letter id: Table B1. Metric Conversion Factors | Table B1. Metric Conversion Factors | text table (headed) |
| 20 | 0 | 612x792 | portrait | 1552 | 1.0 | 227 | - | 0.02, letter id: Table B2. Metric Prefixes; 0.36, letter id: Table B3. Other Physical Conversion Factors | Table B2. Metric Prefixes | text table (headed) |
| 21 | 0 | 612x792 | portrait | 94 | 1.0 | 11 | - | - | Appendix C | divider / blank |
| 22 | 0 | 612x792 | portrait | 6080 | 1.0 | 849 | [0.11, 0.11, 0.11, 0.11, 0.11, 0.11] | 0.07, letter id: Table C1. Population, U.S. Gross Domestic Product, and U.S. Gross Output | Population, U.S. Gross Domestic Product, and U.S. Gross Outp | text table (headed) |
| 23 | 0 | 612x792 | portrait | 116 | 1.0 | 13 | - | - | Appendix D | text (no table heading) |
| 24 | 0 | 612x792 | portrait | 4673 | 1.0 | 824 | [0.12, 0.12, 0.12, 0.12, 0.12] | 0.1, letter id: Table D1. Estimated Primary Energy Consumption in the United States, | Estimated Primary Energy Consumption in the United States, | text table (headed) |
| 25 | 0 | 612x792 | portrait | 2871 | 1.0 | 456 | - | - | Note. Geographic Coverage of Statistics for | text (no table heading) |
| 26 | 0 | 612x792 | portrait | 64 | 1.0 | 5 | - | - | THIS PAGE INTENTIONALLY LEFT BLANK | divider / blank |
| 27 | 0 | 612x792 | portrait | 116 | 1.0 | 11 | - | - | Appendix E | divider / blank |
| 28 | 0 | 612x792 | portrait | 4230 | 1.0 | 618 | - | - | Alternative Measures for the Energy Content of Noncombustibl | text (no table heading) |
| 29 | 0 | 612x792 | portrait | 3161 | 1.0 | 469 | - | - | The incident energy approach converts noncombustible renewab | text (no table heading) |
| 30 | 0 | 612x792 | portrait | 8000 | 1.0 | 1131 | [0.12, 0.12, 0.12, 0.12, 0.12, 0.12] | 0.02, letter id: Table E1. Primary Energy Overview, Fossil Fuel Equivalency Approach | Table E1. Primary Energy Overview, Fossil Fuel Equivalency A | text table (headed) |
| 31 | 0 | 612x792 | portrait | 8013 | 1.0 | 1221 | [0.13, 0.13, 0.13, 0.13, 0.13, 0.13] | 0.02, letter id: Table E2. Primary Energy Production by Source, Fossil Fuel Equivalency Approach | Table E2. Primary Energy Production by Source, Fossil Fuel E | text table (headed) |
| 32 | 0 | 612x792 | portrait | 7642 | 1.0 | 1130 | [0.13, 0.13, 0.13, 0.13, 0.13, 0.13] | 0.02, letter id: Table E3. Primary Energy Consumption by Source, Fossil Fuel Equivalency Approach | Table E3. Primary Energy Consumption by Source, Fossil Fuel  | text table (headed) |
| 33 | 0 | 612x792 | portrait | 9008 | 1.0 | 1504 | [0.13, 0.13, 0.13, 0.13, 0.13, 0.13] | 0.02, letter id: Table E4. Renewable Energy Production and Consumption by Source, Fossil Fuel | Table E4. Renewable Energy Production and Consumption by Sou | text table (headed) |
| 34 | 0 | 612x792 | portrait | 66 | 1.0 | 5 | - | - | THIS PAGE INTENTIONALLY LEFT BLANK | divider / blank |
| 35 | 0 | 612x792 | portrait | 73 | 1.0 | 6 | - | - | Appendix F | divider / blank |
| 36 | 0 | 612x792 | portrait | 7253 | 1.0 | 1171 | [0.11, 0.11, 0.11, 0.11, 0.11, 0.11] | 0.02, letter id: Table F1. Electric Vehicle Charging Infrastructure | Table F1. Electric Vehicle Charging Infrastructure | text table (headed) |
| 37 | 0 | 612x792 | portrait | 3056 | 1.0 | 411 | - | - | Appendix F Methodology and Sources | text (no table heading) |
| 38 | 0 | 612x792 | portrait | 3253 | 1.0 | 509 | - | - |  Charing port information – EV network, EV connector types, | text (no table heading) |
| 39 | 0 | 612x792 | portrait | 4323 | 1.0 | 715 | - | - | Creation of the location and port id | text (no table heading) |
| 40 | 0 | 612x792 | portrait | 1634 | 1.0 | 201 | - | - | seemed to have limited effect on the MER File’s accuracy. Ov | text (no table heading) |

Bookmarks: 16 - p1 MER_A; p2 British Thermal Unit Conversion Factors; p8 MER_A_DOC; p8 Thermal Conversion Factor Source Documentation; p8 Approximate Heat Content of Petroleum and Natural ; p8 Asphalt.  The U.S. Energy Information Administrati; p12 Approximate Heat Content of Biofuels; p13 Approximate Heat Content of Natural Gas; p13 Approximate Heat Content of Coal and Coal Coke; p15 Table A6 Sources; p17 MER_B; p21 MER_C; p23 MER_D; p27 MER_E; p35 MER_F; p37 MER_F_DOC

## sec13 (pilot (burned), data/raw/eia/eia-pdf-sec13.pdf, 22 pages)

| page | /Rotate | w x h | orientation | chars | upright | words | images (page share) | lines naming a table (y, kind: text) | first line | page class |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 0 | 612x792 | portrait | 22 | 1.0 | 1 | - | - | Glossary | divider / blank |
| 2 | 0 | 612x792 | portrait | 4740 | 1.0 | 694 | - | - | Alcohol: The family name of a group of organic chemical comp | text (no table heading) |
| 3 | 0 | 612x792 | portrait | 4475 | 1.0 | 645 | - | - | Biodiesel: Renewable fuel consisting of mono alkyl esters (l | text (no table heading) |
| 4 | 0 | 612x792 | portrait | 4506 | 1.0 | 726 | - | - | Capacity factor: The ratio of the electrical energy produced | text (no table heading) |
| 5 | 0 | 612x792 | portrait | 4694 | 1.0 | 689 | - | - | describes the facilities because some of the plants included | text (no table heading) |
| 6 | 0 | 612x792 | portrait | 4510 | 1.0 | 722 | - | - | Crude oil landed cost: The price of crude oil at the port of | text (no table heading) |
| 7 | 0 | 612x792 | portrait | 4892 | 1.0 | 734 | - | - | Diesel fuel: A fuel composed of distillate fuel oils obtaine | text (no table heading) |
| 8 | 0 | 612x792 | portrait | 4166 | 1.0 | 597 | - | - | Electrical system energy losses: The amount of energy lost d | text (no table heading) |
| 9 | 0 | 612x792 | portrait | 4241 | 1.0 | 648 | - | - | Exploratory well: A well drilled to find and produce oil or  | text (no table heading) |
| 10 | 0 | 612x792 | portrait | 4740 | 1.0 | 741 | - | - | Gas turbine plant: A plant in which the prime mover is a gas | text (no table heading) |
| 11 | 0 | 612x792 | portrait | 4338 | 1.0 | 639 | - | - | Hydroelectric pumped storage: Hydroelectricity that is gener | text (no table heading) |
| 12 | 0 | 612x792 | portrait | 4670 | 1.0 | 702 | - | - | Kerosene: A light petroleum distillate that is used in space | text (no table heading) |
| 13 | 0 | 612x792 | portrait | 4638 | 1.0 | 654 | - | - | Methanol (CH OH): A light, volatile alcohol eligible for gas | text (no table heading) |
| 14 | 0 | 612x792 | portrait | 4544 | 1.0 | 661 | - | - | Motor gasoline retail prices: Motor gasoline prices calculat | text (no table heading) |
| 15 | 0 | 612x792 | portrait | 4025 | 1.0 | 602 | - | - | Natural gasoline: A commodity product commonly traded in nat | text (no table heading) |
| 16 | 0 | 612x792 | portrait | 4413 | 1.0 | 615 | - | - | Olefins: See Olefinic hydrocarbons (olefins). | text (no table heading) |
| 17 | 0 | 612x792 | portrait | 4521 | 1.0 | 655 | - | - | Paraffinic hydrocarbons: Saturated hydrocarbon compounds wit | text (no table heading) |
| 18 | 0 | 612x792 | portrait | 5267 | 1.0 | 738 | - | - | Primary energy consumption: Consumption of primary energy. E | text (no table heading) |
| 19 | 0 | 612x792 | portrait | 4336 | 1.0 | 632 | - | - | renewable fuels (including fuel ethanol). Also included are  | text (no table heading) |
| 20 | 0 | 612x792 | portrait | 4167 | 1.0 | 626 | - | - | SIC (Standard Industrial Classification): A set of codes dev | text (no table heading) |
| 21 | 0 | 612x792 | portrait | 4461 | 1.0 | 636 | - | - | Synthetic natural gas (SNG): (Also referred to as substitute | text (no table heading) |
| 22 | 0 | 612x792 | portrait | 2681 | 1.0 | 420 | - | - | Vented natural gas: Natural gas released into the air on the | text (no table heading) |

Bookmarks: 0

## Export check (`xls.php?tbl=`; type and export title only)

| tbl | type | export title |
|---|---|---|
| T07.01 | OOXML (xlsx) | Table 7.1 Electricity Overview |
| T07.02B | OOXML (xlsx) | Table 7.2b Electricity Net Generation: Electric Power Sector |
| T07.02C | OOXML (xlsx) | Table 7.2c Electricity Net Generation: Commercial and Industrial Sectors |
| T07.03B | OOXML (xlsx) | Table 7.3b Consumption of Combustible Fuels for Electricity Generation: Electric Power Sec |
| T07.04B | OOXML (xlsx) | Table 7.4b Consumption of Combustible Fuels for Electricity Generation and Useful Thermal  |
| T07.06 | OOXML (xlsx) | Table 7.6 Electricity End Use and Electric Vehicle Use |
| T07.07B | OOXML (xlsx) | Table 7.7b Electric Net Summer Capacity: Electric Power Sector |
| T07.02A | OOXML (xlsx) | Table 7.2a Electricity Net Generation: Total (All Sectors) |
| T07.03A | OOXML (xlsx) | Table 7.3a Consumption of Combustible Fuels for Electricity Generation: Total (All Sectors |
| T07.03C | OOXML (xlsx) | Table 7.3c Consumption of Selected Combustible Fuels for Electricity Generation: Commercia |
| T07.04A | OOXML (xlsx) | Table 7.4a Consumption of Combustible Fuels for Electricity Generation and Useful Thermal  |
| T07.04C | OOXML (xlsx) | Table 7.4c Consumption of Selected Combustible Fuels for Electricity Generation and Useful |
| T07.05 | OOXML (xlsx) | Table 7.5 Stocks of Coal and Petroleum:  Electric Power Sector |
| T07.07A | OOXML (xlsx) | Table 7.7a Electric Net Summer Capacity: Total (All Sectors) |
| T07.07C | OOXML (xlsx) | Table 7.7c Electric Net Summer Capacity: Commercial Sector |
| TA1 | OOXML (xlsx) |  |
| TA2 | OOXML (xlsx) | Table A2 Approximate Heat Content of  Petroleum Production, Imports, and Exports |
| TA3 | OOXML (xlsx) | Table A3 Approximate Heat Content of Petroleum Consumption and Fuel Ethanol |
| TA4 | OOXML (xlsx) | Table A4 Approximate Heat Content of Natural Gas |
| TA5 | OOXML (xlsx) | Table A5 Approximate Heat Content of Coal and Coke Coal |
| TA6 | OOXML (xlsx) | Table A6: Approximate heat rates for electricity, and heat content of electricity |
| TB1 | OOXML (xlsx) |  |
| TB2 | OOXML (xlsx) |  |
| TB3 | OOXML (xlsx) |  |
| TC1 | OOXML (xlsx) | Table C1 Population, U.S. Gross Domestic Product, and U.S. Gross Output |
| TD1 | OOXML (xlsx) |  |
| TE1 | OOXML (xlsx) | Table E1. Primary Energy Overview, Fossil Fuel Equivalency Approach |
| TE2 | OOXML (xlsx) | Table E2. Primary Energy Production by Source, Fossil Fuel Equivalency Approach |
| TE3 | OOXML (xlsx) | Table E3. Primary Energy Consumption by Source, Fossil Fuel Equivalency Approach |
| TE4 | OOXML (xlsx) | Table E4. Renewable Energy Production and Consumption by Source, Fossil Fuel Equivalency A |
| TF1 | OOXML (xlsx) | Table F1. Electric Vehicle Charging Infrastructure |
| TA01 | OOXML (xlsx) |  |
| TA02 | OOXML (xlsx) |  |
| TA03 | OOXML (xlsx) |  |
| TA04 | OOXML (xlsx) |  |
| TA05 | OOXML (xlsx) |  |
| TA06 | OOXML (xlsx) |  |
| TB01 | OOXML (xlsx) |  |
| TB02 | OOXML (xlsx) |  |
| TB03 | OOXML (xlsx) |  |
| TC01 | OOXML (xlsx) |  |
| TD01 | OOXML (xlsx) |  |
| TE01 | OOXML (xlsx) |  |
| TE02 | OOXML (xlsx) |  |
| TE03 | OOXML (xlsx) |  |
| TE04 | OOXML (xlsx) |  |
| TF01 | OOXML (xlsx) |  |

Fetch hosts: {'www.eia.gov': 47}

