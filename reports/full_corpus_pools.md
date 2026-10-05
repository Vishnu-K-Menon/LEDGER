# Full-corpus eligible pools (read-only listing; nothing drawn, fetched or parsed)

Generated 2026-10-05T03:20:43+00:00 · snapshot cut-off **2026-09-20** (the pilot's, D-034) · `data/manifest.jsonl` sha256 unchanged (`a754fc53a6d8…`), 20 units in it.

**No draw, no PDF fetch, no parse, nothing under `data/` written.** `run_listing` (`ledger/ingest/listing.py:93`, writes the manifest at :377) was not called; the script is `scripts/list_full_corpus.py`.

## Functions reused

- `ledger/ingest/http.py`: `Fetcher` :28 (`calls_by_host` :39), `govinfo_api_key` :130
- `ledger/ingest/govinfo.py`: `published` :105, `package_summary` :133, `granules` :143, `granule_summary` :167, `series_key` :184, `latest_per_series` :194, `gate` :205
- `ledger/ingest/listing.py`: `resolvable_reports` :75 (calls `report_pdf_link` :58)
- `ledger/ingest/eia.py`: `sitemap_lists` :27, `list_units` :45, `HREF_PDF` :14, `_disallowed` :41
- `ledger/ingest/frames.py`: `parse_frames` (read-only; `write_candidates_csv` not called)
- `ledger/ingest/manifest.py`: `read_manifest`

## Readings applied

- Window: `published(<collection>, 2023-01-01, 2026-09-20)` is eligible; packages with dateIssued 2026-09-21 or later are listed separately as **after snapshot** and are not eligible.
- D-034 one edition per series (`latest_per_series`, series from the package id), computed inside the pre-snapshot window. A series already in the pilot is ineligible in every edition (report-level BUDGET). ERP is granule-level: ERP-2026 stays the one edition and the exclusion is per unit (the pilot's two granules); ERP-2023..2025 are ineligible by the one-edition rule.
- pdfLink rule (`resolvable_reports`), MER excluded (`corpus.excluded_parent_series`), `govinfo_crpt` = 0 (no CRPT call), every unit in the manifest excluded whatever its status.
- ECONI is a D-034 source (`docs/decisions.md:419`, `configs/base.yaml:25`, one edition only in the full corpus, none in the pilot); D-040's composition line does not mention it. Reported in full.

## govinfo_budget

- Packages in the window: 40 · distinct series 13 · latest per series 13
- Removed (series already in the pilot, every edition): BUDGET-2026-CROSSCUT, BUDGET-2026-DOD, BUDGET-2027-BALANCES, BUDGET-2027-FCS, BUDGET-2027-TAB
- Candidates: 8 · no resolvable pdfLink: 2 · already in the manifest: 0 · **eligible: 6**
  - unresolvable: BUDGET-2025-LRB: no package pdfLink and 0 granules; not resolvable
  - unresolvable: BUDGET-2027-DB: no package pdfLink and 4 granules; not resolvable
- Unit-kind gate (as `run_listing` runs it, on the latest-per-series set): **report-level** · pdfLink fail · pages field-absent · self-contained field-absent · boundary field-absent
- Series with a newer edition after the snapshot: none

| package id | series | title | dateIssued | pages | pdfLink source | est. parse 9–19 s/page |
|---|---|---|---|---|---|---|
| BUDGET-2025-CLIMATE | BUDGET-CLIMATE | Climate Risk Analysis | 2024-03-11 | None | single granule BUDGET-2025-CLIMATE-1 pdfLink | pages unknown |
| BUDGET-2027-MSR | BUDGET-MSR | Mid-Session Review | 2026-09-04 | 12 | package pdfLink | 0.0 h–0.1 h |
| BUDGET-2027-OBJCLASS | BUDGET-OBJCLASS | Object Class Analysis | 2026-04-03 | 89 | package pdfLink | 0.2 h–0.5 h |
| BUDGET-2027-BUD | BUDGET-BUD | Budget of the U.S. Government | 2026-04-03 | 92 | package pdfLink | 0.2 h–0.5 h |
| BUDGET-2027-PER | BUDGET-PER | Analytical Perspectives | 2026-04-03 | 158 | package pdfLink | 0.4 h–0.8 h |
| BUDGET-2027-APP | BUDGET-APP | Appendix | 2026-04-03 | 1340 | package pdfLink | 3.4 h–7.1 h |

**Page distribution (eligible volumes, package metadata pages):** n 5 · min 12 · Q1 89.0 · median 92.0 · Q3 158.0 · max 1340

| page cap | volumes under the cap |
|---|---|
| < 100 | 3 |
| < 200 | 4 |
| < 300 | 4 |
| < 500 | 4 |

Pages missing in metadata: BUDGET-2025-CLIMATE

After snapshot (not eligible): none

## govinfo_erp

- One edition: **ERP-2026** (450 pages, 80 granules). Other editions in the window (ineligible, one-edition rule): ERP-2025, ERP-2024, ERP-2023
- Granule classes: {'APPENDIX': 2, 'CHAPTER': 14, 'FRONTMATTER': 1, 'OTHER': 1, 'TABLE': 61, 'TOC': 1} · TABLE granules 61 · removed (pilot): ERP-2026-table22, ERP-2026-table4 · **eligible TABLE granules: 59**
- **Pages are an ESTIMATE:** package pages ÷ granules = **6** per granule. That estimate overstated the pilot (6 estimated vs 2 measured, D-034 status 2026-09-20 (d)); granule summaries carry `pages` for 0 of 59. Measured size is expected to be nearer 2 pages, i.e. ~30 s/granule at 15.0 s/page.
- Granules without a pdfLink: none

**Held-out set, `data/oracle/fresh/erp_draw.json` (D-039 rung-1b; burned for the oracle). Listed, not included or excluded:**

| granule | in the eligible pool | local PDF (`data/raw_fresh`) | local xls (`data/oracle/fresh/erp`) |
|---|---|---|---|
| ERP-2026-table33 | yes | yes | yes |
| ERP-2026-table43 | yes | yes | yes |
| ERP-2026-table52 | yes | yes | yes |
| ERP-2026-table7 | yes | yes | yes |
| ERP-2026-table28 | yes | yes | yes |
| ERP-2026-table10 | yes | yes | yes |
| ERP-2026-table14 | yes | yes | yes |
| ERP-2026-table59 | yes | yes | yes |

<details><summary>Eligible TABLE granules (est. pages, not measured)</summary>

| granule | title | pages (metadata) | pages (estimate) | held-out |
|---|---|---|---|---|
| ERP-2026-table1 | Percent changes in real gross domestic product, 1975-2025 | None | 6 |  |
| ERP-2026-table2 | Contributions to percent change in real gross domestic product, 1975-2 | None | 6 |  |
| ERP-2026-table3 | Gross domestic product, 2010-2025 | None | 6 |  |
| ERP-2026-table5 | Chain-type price indexes for gross domestic product, 1975-2025 | None | 6 |  |
| ERP-2026-table6 | Gross value added by sector, 1975-2025 | None | 6 |  |
| ERP-2026-table7 | Real gross value added by sector, 1975-2025 | None | 6 | yes |
| ERP-2026-table8 | Gross domestic product (GDP) by industry, value added, in current doll | None | 6 |  |
| ERP-2026-table9 | Real gross domestic product by industry, value added, and percent chan | None | 6 |  |
| ERP-2026-table10 | Personal consumption expenditures, 1975-2025 | None | 6 | yes |
| ERP-2026-table11 | Real personal consumption expenditures, 2007-2025 | None | 6 |  |
| ERP-2026-table12 | Private fixed investment by type, 1975-2025 | None | 6 |  |
| ERP-2026-table13 | Real private fixed investment by type, 2007-2025 | None | 6 |  |
| ERP-2026-table14 | Foreign transactions in the national income and product accounts, 1975 | None | 6 | yes |
| ERP-2026-table15 | Real exports and imports of goods and services, 2007-2025 | None | 6 |  |
| ERP-2026-table16 | Sources of personal income, 1975-2025 | None | 6 |  |
| ERP-2026-table17 | Disposition of personal income, 1975-2025 | None | 6 |  |
| ERP-2026-table18 | Total and per capita disposable personal income and personal consumpti | None | 6 |  |
| ERP-2026-table19 | Gross saving and investment, 1975-2025 | None | 6 |  |
| ERP-2026-table20 | Median money income (in 2024 dollars) and poverty status of families a | None | 6 |  |
| ERP-2026-table21 | Real farm income, 1960-2026 | None | 6 |  |
| ERP-2026-table23 | Civilian employment by sex, age, and demographic characteristic, 1980- | None | 6 |  |
| ERP-2026-table24 | Unemployment by sex, age, and demographic characteristic, 1980-2025 | None | 6 |  |
| ERP-2026-table25 | Civilian labor force participation rate, 1980-2025 | None | 6 |  |
| ERP-2026-table26 | Civilian employment/population ratio, 1980-2025 | None | 6 |  |
| ERP-2026-table27 | Civilian unemployment rate, 1980-2025 | None | 6 |  |
| ERP-2026-table28 | Unemployment by duration and reason, 1980-2025 | None | 6 | yes |
| ERP-2026-table29 | Employees on nonagricultural payrolls, by major industry, 1980-2025 | None | 6 |  |
| ERP-2026-table30 | Hours and earnings in private nonagricultural industries, 1980-2025 | None | 6 |  |
| ERP-2026-table31 | Employment cost index, private industry, 2008-2025 | None | 6 |  |
| ERP-2026-table32 | Productivity and related data, business and nonfarm business sectors,  | None | 6 |  |
| ERP-2026-table33 | Changes in productivity and related data, business and nonfarm busines | None | 6 | yes |
| ERP-2026-table34 | Industrial production indexes, major industry divisions, 1980-2025 | None | 6 |  |
| ERP-2026-table35 | Capacity utilization rates, 1980-2025 | None | 6 |  |
| ERP-2026-table36 | New private housing units started, authorized, and completed and house | None | 6 |  |
| ERP-2026-table37 | Manufacturing and trade sales and inventories, 1983-2025 | None | 6 |  |
| ERP-2026-table38 | Changes in consumer price indexes, 1984-2025 | None | 6 |  |
| ERP-2026-table39 | Price indexes for personal consumption expenditures, and percent chang | None | 6 |  |
| ERP-2026-table40 | Money stock and debt measures, 1990-2025 | None | 6 |  |
| ERP-2026-table41 | Consumer credit outstanding, 1977-2025 | None | 6 |  |
| ERP-2026-table42 | Bond yields and interest rates, 1955-2025 | None | 6 |  |
| ERP-2026-table43 | Mortgage debt outstanding by type of property and of financing, 1967-2 | None | 6 | yes |
| ERP-2026-table44 | Mortgage debt outstanding by holder, 1967-2025 | None | 6 |  |
| ERP-2026-table45 | Federal receipts, outlays, surplus or deficit, and debt, fiscal years  | None | 6 |  |
| ERP-2026-table46 | Federal receipts, outlays, surplus or deficit, and debt, as percent of | None | 6 |  |
| ERP-2026-table47 | Federal receipts and outlays, by major category, and surplus or defici | None | 6 |  |
| ERP-2026-table48 | Federal receipts, outlays, surplus or deficit, and debt, fiscal years  | None | 6 |  |
| ERP-2026-table49 | Federal and State and local government current receipts and expenditur | None | 6 |  |
| ERP-2026-table50 | State and local government revenues and expenditures, fiscal years 196 | None | 6 |  |
| ERP-2026-table51 | U.S. Treasury securities outstanding by kind of obligation, 1985-2025 | None | 6 |  |
| ERP-2026-table52 | Estimated ownership of U.S. Treasury securities, 2011-2025 | None | 6 | yes |
| ERP-2026-table53 | Corporate profits with inventory valuation and capital consumption adj | None | 6 |  |
| ERP-2026-table54 | Corporate profits by industry, 1975-2025 | None | 6 |  |
| ERP-2026-table55 | Historical stock prices and yields, 1949-2003 | None | 6 |  |
| ERP-2026-table56 | Common stock prices and yields, 2000-2025 | None | 6 |  |
| ERP-2026-table57 | U.S. international transactions, 1977-2025 | None | 6 |  |
| ERP-2026-table58 | U.S. international trade in goods on balance of payments (BOP) and Cen | None | 6 |  |
| ERP-2026-table59 | U.S. international trade in goods and services by area and country, 20 | None | 6 | yes |
| ERP-2026-table60 | Foreign exchange rates, 2005-2025 | None | 6 |  |
| ERP-2026-table61 | Growth rates in real gross domestic product by area and country, 2007- | None | 6 |  |

</details>

## govinfo_econi (one edition only, D-034)

- Packages in the window: 43 · series: ECONI
- **Latest pre-snapshot edition: ECONI-2026-08** · dateIssued 2026-08-01 · pages 40 · granules 48 · in manifest: False
- Unit-kind gate (as `run_listing` decides): **granule-level** · pdfLink pass · pages field-absent · self-contained field-absent · boundary field-absent
  - gate: granule summaries carry no `pages`; fallback = package pages / granule count (pages_source: estimated) until --stage fetch measures the file
  - gate: ECONI-2026-08-Pg1: txtLink rendition is a stub (269 chars) -> unjudgeable from metadata
  - gate: ECONI-2026-08-Pg19: txtLink rendition is a stub (242 chars) -> unjudgeable from metadata
  - gate: ECONI-2026-08-Pg37: txtLink rendition is a stub (255 chars) -> unjudgeable from metadata

| granule | class | title | pages (metadata) | pages (estimate) | pdfLink | in manifest |
|---|---|---|---|---|---|---|
| ECONI-2026-08-Pg1 | CONTENT | GROSS DOMESTIC PRODUCT | None | 1 | yes | False |
| ECONI-2026-08-Pg2 | CONTENT | REAL GROSS DOMESTIC PRODUCT | None | 1 | yes | False |
| ECONI-2026-08-Pg2-1 | CONTENT | CHAINED PRICE INDEXES FOR GROSS DOMESTIC PRODUCT | None | 1 | yes | False |
| ECONI-2026-08-Pg3 | CONTENT | GROSS DOMESTIC PRODUCT AND RELATED PRICE MEASURES: INDEXES A | None | 1 | yes | False |
| ECONI-2026-08-Pg3-1 | CONTENT | NONFINANCIAL CORPORATE BUSINESS--GROSS VALUE ADDED AND PRICE | None | 1 | yes | False |
| ECONI-2026-08-Pg4 | CONTENT | NATIONAL INCOME | None | 1 | yes | False |
| ECONI-2026-08-Pg4-1 | CONTENT | REAL PERSONAL CONSUMPTION EXPENDITURES | None | 1 | yes | False |
| ECONI-2026-08-Pg5 | CONTENT | SOURCES OF PERSONAL INCOME | None | 1 | yes | False |
| ECONI-2026-08-Pg6 | CONTENT | DISPOSITION OF PERSONAL INCOME | None | 1 | yes | False |
| ECONI-2026-08-Pg7 | CONTENT | REAL FARM INCOME | None | 1 | yes | False |
| ECONI-2026-08-Pg8 | CONTENT | CORPORATE PROFITS | None | 1 | yes | False |
| ECONI-2026-08-Pg9 | CONTENT | REAL GROSS PRIVATE DOMESTIC INVESTMENT | None | 1 | yes | False |
| ECONI-2026-08-Pg10 | CONTENT | REAL PRIVATE FIXED INVESTMENT BY TYPE | None | 1 | yes | False |
| ECONI-2026-08-Pg10-1 | CONTENT | BUSINESS INVESTMENT | None | 1 | yes | False |
| ECONI-2026-08-Pg11 | CONTENT | STATUS OF THE LABOR FORCE | None | 1 | yes | False |
| ECONI-2026-08-Pg12 | CONTENT | SELECTED UNEMPLOYMENT RATES | None | 1 | yes | False |
| ECONI-2026-08-Pg13 | CONTENT | SELECTED MEASURES OF UNEMPLOYMENT AND UNEMPLOYMENT INSURANCE | None | 1 | yes | False |
| ECONI-2026-08-Pg14 | CONTENT | NONAGRICULTURAL EMPLOYMENT | None | 1 | yes | False |
| ECONI-2026-08-Pg15 | CONTENT | AVERAGE WEEKLY HOURS, HOURLY EARNINGS, AND WEEKLY EARNINGS-- | None | 1 | yes | False |
| ECONI-2026-08-Pg15-1 | CONTENT | EMPLOYMENT COST INDEX--PRIVATE INDUSTRY | None | 1 | yes | False |
| ECONI-2026-08-Pg16 | CONTENT | PRODUCTIVITY AND RELATED DATA, BUSINESS AND NONFARM BUSINESS | None | 1 | yes | False |
| ECONI-2026-08-Pg17 | CONTENT | INDUSTRIAL PRODUCTION AND CAPACITY UTILIZATION | None | 1 | yes | False |
| ECONI-2026-08-Pg18 | CONTENT | INDUSTRIAL PRODUCTION--MAJOR MARKET GROUPS | None | 1 | yes | False |
| ECONI-2026-08-Pg18-1 | CONTENT | INDUSTRIAL PRODUCTION--SELECTED MANUFACTURES | None | 1 | yes | False |
| ECONI-2026-08-Pg19 | CONTENT | NEW CONSTRUCTION | None | 1 | yes | False |
| ECONI-2026-08-Pg19-1 | CONTENT | NEW PRIVATE HOUSING AND VACANCY RATES | None | 1 | yes | False |
| ECONI-2026-08-Pg20 | CONTENT | BUSINESS SALES AND INVENTORIES--MANUFACTURING AND TRADE | None | 1 | yes | False |
| ECONI-2026-08-Pg21 | CONTENT | MANUFACTURERS' SHIPMENTS, INVENTORIES, AND ORDERS | None | 1 | yes | False |
| ECONI-2026-08-Pg22 | CONTENT | PRODUCER PRICES | None | 1 | yes | False |
| ECONI-2026-08-Pg23 | CONTENT | CONSUMER PRICES--ALL URBAN CONSUMERS | None | 1 | yes | False |
| ECONI-2026-08-Pg24 | CONTENT | CHANGES IN PRODUCER PRICES | None | 1 | yes | False |
| ECONI-2026-08-Pg24-1 | CONTENT | CHANGES IN CONSUMER PRICES--ALL URBAN CONSUMERS | None | 1 | yes | False |
| ECONI-2026-08-Pg25 | CONTENT | PRICES RECEIVED AND PAID BY FARMERS | None | 1 | yes | False |
| ECONI-2026-08-Pg26 | CONTENT | MONEY STOCK AND DEBT MEASURES | None | 1 | yes | False |
| ECONI-2026-08-Pg27 | CONTENT | COMPONENTS OF MONEY STOCK | None | 1 | yes | False |
| ECONI-2026-08-Pg27-1 | CONTENT | AGGREGATE RESERVES AND MONETARY BASE | None | 1 | yes | False |
| ECONI-2026-08-Pg28 | CONTENT | BANK CREDIT AT ALL COMMERCIAL BANKS | None | 1 | yes | False |
| ECONI-2026-08-Pg29 | CONTENT | SOURCES AND USES OF FUNDS, NONFARM NONFINANCIAL CORPORATE BU | None | 1 | yes | False |
| ECONI-2026-08-Pg29-1 | CONTENT | CONSUMER CREDIT | None | 1 | yes | False |
| ECONI-2026-08-Pg30 | CONTENT | INTEREST RATES AND BOND YIELDS | None | 1 | yes | False |
| ECONI-2026-08-Pg31 | CONTENT | COMMON STOCK PRICES AND YIELDS | None | 1 | yes | False |
| ECONI-2026-08-Pg32 | CONTENT | FEDERAL RECEIPTS, OUTLAYS, AND DEBT | None | 1 | yes | False |
| ECONI-2026-08-Pg33 | CONTENT | FEDERAL RECEIPTS BY SOURCE AND OUTLAYS BY FUNCTION | None | 1 | yes | False |
| ECONI-2026-08-Pg34 | CONTENT | FEDERAL SECTOR, NATIONAL INCOME ACCOUNTS BASIS | None | 1 | yes | False |
| ECONI-2026-08-Pg35 | CONTENT | INDUSTRIAL PRODUCTION AND CONSUMER PRICES--MAJOR INDUSTRIAL  | None | 1 | yes | False |
| ECONI-2026-08-Pg35-1 | CONTENT | U.S. INTERNATIONAL TRADE IN GOODS AND SERVICES | None | 1 | yes | False |
| ECONI-2026-08-Pg36 | CONTENT | U.S. INTERNATIONAL TRANSACTIONS | None | 1 | yes | False |
| ECONI-2026-08-Pg37 | CONTENT | U.S. INTERNATIONAL TRANSACTIONS--CONTINUED | None | 1 | yes | False |

**Parse-time ESTIMATE at 15.0 s/page:** 48 pages (metadata where present, else estimate) ≈ 720 s (0.2 h); one edition only, so this is the whole ECONI cost.

After snapshot (not eligible): none

## eia

- Frame: sitemap → three landing pages → PDF links (sitemap flags: {'mer': True, 'steo': True, 'aeo': True, '_is_index': False, '_pdf_count': 0, '_url_count': 133}). Frame units found: 15 (MER sections + STEO full + AEO narrative).

| unit | series | MER excluded (D-040) | in manifest | eligible |
|---|---|---|---|---|
| eia-pdf-AEO_Narrative | aeo | False | True | no |
| eia-pdf-sec1 | mer | True | True | no |
| eia-pdf-sec2 | mer | True | False | no |
| eia-pdf-sec3 | mer | True | True | no |
| eia-pdf-sec4 | mer | True | True | no |
| eia-pdf-sec5 | mer | True | False | no |
| eia-pdf-sec6 | mer | True | False | no |
| eia-pdf-sec7 | mer | True | False | no |
| eia-pdf-sec8 | mer | True | True | no |
| eia-pdf-sec9 | mer | True | False | no |
| eia-pdf-sec10 | mer | True | False | no |
| eia-pdf-sec11 | mer | True | True | no |
| eia-pdf-sec12 | mer | True | False | no |
| eia-pdf-sec13 | mer | True | True | no |
| eia-pdf-steo_full | steo | False | True | no |

**Eligible EIA units: 0.**

Other PDF links on the landing pages, outside the frame filter (information only; not part of the D-034 frame, not eligible unless the frame is widened). Counts per landing page:

- mer: 196 links (all MER, excluded by D-040); robots-disallowed 0
- steo: 3 links; robots-disallowed 0
- aeo: 6 links; robots-disallowed 0
  - steo: https://www.eia.gov/outlooks/steo/pdf/compare.pdf
  - steo: https://www.eia.gov/outlooks/steo/pdf/steo_text.pdf
  - steo: https://www.eia.gov/outlooks/steo/pdf/compare.pdf
  - aeo: https://www.eia.gov/outlooks/aeo/nems/overview/pdf/0581(2023).pdf
  - aeo: https://www.eia.gov/outlooks/aeo/pdf/2026/AEO2026_EMMTimeslices.pdf
  - aeo: https://www.eia.gov/outlooks/aeo/pdf/2026/AEO2026_HSM_Prod.pdf
  - aeo: https://www.eia.gov/outlooks/aeo/pdf/2026/AEO2026_LNGexports.pdf
  - aeo: https://www.eia.gov/outlooks/aeo/pdf/2026/OBBBA_Assumptions.pdf
  - aeo: https://www.eia.gov/outlooks/aeo/pdf/AEO2026_Release_Presentation.pdf

The full list is in `reports/full_corpus_pools.json` (`eia.other_pdf_links_outside_frame`).

## cbo_manual

- `data/manual/cbo/sources.csv` (utf-8-sig): **4 rows**, 4 already in the manifest.
- Local frame files (`data/frames/frame_<year>.html`, parsed read-only): 40 candidates, **36 not in the manifest**. cbo.gov is never contacted by script; acquisition stays the owner's, so pages are unknown until fetched (pilot CBO units: [2, 2, 3, 5] pages).

<details><summary>Frame candidates not in the manifest</summary>

- cbo-59853 · 2023 · 2023-12-22 · H.R. 3196, Architect of the Capitol Appointment Act of 2023
- cbo-59852 · 2023 · 2023-12-22 · S. 1258, Billion Dollar Boondoggle Act of 2023
- cbo-59847 · 2023 · 2023-12-21 · S. 776, M.H. Dutch Salmon Greater Gila Wild and Scenic River Act
- cbo-59846 · 2023 · 2023-12-21 · H.R. 6586, A bill to require a strategy to oppose financial or material support 
- cbo-59828 · 2023 · 2023-12-21 · H.R. 5914, Veterans Education Transparency and Training Act
- cbo-59810 · 2023 · 2023-12-21 · H.R. 5375, Strengthening the Quad Act
- cbo-59842 · 2023 · 2023-12-20 · H.R. 522, Deliver for Veterans Act
- cbo-59835 · 2023 · 2023-12-20 · H.R. 3722, Daniel J. Harvey, Jr. and Adam Lambert Improving Servicemember Transi
- cbo-59834 · 2023 · 2023-12-20 · H.R. 5785, Edith Nourse Rogers STEM Scholarship Opportunity Act
- cbo-61118 · 2024 · 2024-12-20 · H.R. 8816, American Medical Innovation and Investment Act of 2024
- cbo-60627 · 2024 · 2024-08-12 · H.R. 8446, Critical Mineral Consistency Act of 2024
- cbo-60629 · 2024 · 2024-08-14 · S. 3875, AI Transparency in Elections Act of 2024
- cbo-60972 · 2024 · 2024-11-08 · Estimate of H.R. 8467 Relative to CBO’s June 2024 Baseline Projections
- cbo-60981 · 2024 · 2024-11-14 · S. 3757, Congenital Heart Futures Reauthorization Act of 2024
- cbo-61099 · 2024 · 2024-12-11 · S. 4043, Telework Transparency Act of 2024
- cbo-61096 · 2024 · 2024-12-11 · S. 3015, Telework Reform Act of 2024
- cbo-61071 · 2024 · 2024-12-06 · S. 3162, TEST AI Act of 2024
- cbo-60767 · 2024 · 2024-09-25 · S. 1956, Invent Here, Make Here Act of 2024
- cbo-61956 · 2025 · 2025-12-19 · H.R. 6338, Stop Illegal Fishing Act
- cbo-61958 · 2025 · 2025-12-19 · H.R. 1848, Houthi Human Rights Accountability Act
- cbo-61957 · 2025 · 2025-12-19 · H.R. 4291, Sanctions Lists Harmonization Act
- cbo-61964 · 2025 · 2025-12-19 · H.R. 5021, American Decade of Sports Act
- cbo-61965 · 2025 · 2025-12-17 · S. 1070, National STEM Week Act
- cbo-61961 · 2025 · 2025-12-16 · S. 2245, a bill to amend the Digital Coast Act to improve the acquisition, integ
- cbo-61934 · 2025 · 2025-12-15 · H.R. 4638, Bill to Outlaw Wounding of Official Working Animals Act of 2025
- cbo-61720 · 2025 · 2025-12-12 · Legislation considered under suspension of the Rules of the House of Representat
- cbo-61938 · 2025 · 2025-12-10 · Estimated Budgetary Effects of S. 3385, the Lower Health Care Costs Act
- cbo-62772 · 2026 · 2026-09-17 · S. 4259, Blue Skies for Taiwan Act of 2026
- cbo-62774 · 2026 · 2026-09-17 · H.R. 1640, HEIRS Act of 2025
- cbo-62773 · 2026 · 2026-09-17 · S. 2801, Canterbury Shaker Village National Heritage Area Study Authorization Ac
- cbo-62771 · 2026 · 2026-09-15 · S. 164, Midnight Rules Relief Act of 2025
- cbo-62765 · 2026 · 2026-09-11 · S. 4570, U.S. Technology Procurement and Access to Trusted Hardware Act
- cbo-62720 · 2026 · 2026-09-11 · S. 4429, Connected Vehicle Security Act of 2026
- cbo-62589 · 2026 · 2026-09-11 · Legislation considered under suspension of the Rules of the House of Representat
- cbo-62770 · 2026 · 2026-09-10 · H.R. 9342, GPO Modernization Act of 2026
- cbo-62769 · 2026 · 2026-09-10 · H.R. 3334, USCP Empowerment Act of 2025

</details>

## Parse-time ESTIMATES (not measurements)

Rates from `docs/plan.md` T3: BUDGET 9–19 s/page, CBO 2.5–5 s/page, 15.0 s/page otherwise. Pages are package metadata (BUDGET, ECONI), the ERP per-granule estimate (overstated on the pilot), and for CBO the pilot's mean pages × the candidates not yet in the manifest. Pools, not draws.

| source | pool pages (estimate) | parse, low | parse, high |
|---|---|---|---|
| budget | 1691 | 4.2 h | 8.9 h |
| erp | 354 | 1.5 h | 1.5 h |
| econi | 40 | 0.2 h | 0.2 h |
| cbo | 108 | 0.1 h | 0.1 h |
| eia | 0 | 0.0 h | 0.0 h |

BUDGET pages exclude packages whose metadata carries none (listed in the BUDGET section).

**An 8-hour overnight parse fits ≈ 3,200 BUDGET pages at 9 s/page and ≈ 1,515 pages at 19 s/page.**

A unit can still be excluded at fetch under the image-only rule (D-034 status 2026-10-02: ≥ 1 image and ≤ 20 words on ≥ 25 % of pages), with **no replacement draw**, so the realised unit count can fall below the draw.

## HTTP calls

Total **377** GETs through `Fetcher` (robots.txt GETs, one per host, are not counted by it):

- api.govinfo.gov: 370
- www.eia.gov: 7
- www.cbo.gov / www.gao.gov: 0 (never contacted)
