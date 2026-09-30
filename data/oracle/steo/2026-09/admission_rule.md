# STEO oracle admission rule (council ruling, adopted by the owner 2026-09-29)

Applies to the STEO 2026-09 snapshot in this directory ("STEO 2026-09, release 2026-09-09";
hashes in `sources.json`) against the printed tables of the held `steo_full.pdf`
(sha256 `c7af46960225fac0b8be4cbd0d4d3d886c24f5c6c771ccac3ca33eb0adce271a`), pages 31-56.
Committed, with its implementation (`scripts/a1_diag/steo.py::admit_table_rows`), **before any
parser output is scored against STEO**.

## The rule

A printed row is **admitted** iff all three hold:

- **(a) Values.** Every non-"-" cell of the row equals the served value of one series, rounded
  **half away from zero** at the **printed** number of decimals of that cell.
  - The served value is a `Decimal` built from the served string (never a binary float).
  - Printed tokens are parsed from the **PDF text layer**, never from the parse: thousands
    separators are stripped; "-", U+2212 and parenthesised negatives are read as negative.
  - A cell printed as "-" is expected-empty and is not a value.
- **(b) Uniqueness.** Exactly one served series in the table's browser view satisfies (a).
  - Series are distinct `SERIES_ID`s; the same series listed twice in a view is one series.
  - Zero satisfying series: the row is unmapped.
  - Two or more: the row is a tie and fails uniqueness.
- **(c) Content.** The row has at least one non-"-" cell and at least two distinct printed values.

An admitted row's cells are all admitted. Its identity is the one series that satisfies (a).

## Recorded, not gated

These are recorded per admitted row as columns and never decide admission:

- printed unit string and served `UNITS`;
- the unit verdict: equal / normalised / alias / mismatch, with the alias list frozen at
  `unit_aliases.json` sha256 `4e080e3a56e9f337b09b74abc65cea28609dfa238193eda6608eee05bd0f27e6`;
- served `PRECISION` beside the printed decimals;
- `n_matched`: the number of served series satisfying (a);
- whether a printed unit string is present;
- whether the printed label matches the series' `DESCRIPTION` or `CHART_NAME`;
- every metadata disagreement (unit, precision, label).

## Also recorded

- **Footnoted rows**, from the frozen `footnotes.json`: a stratum, never a gate.
- **History and forecast strata**, from the series' `LAST_HISTORICAL` (`YYYY0q`) and the annual
  view's (`YYYY`).
- **"-" cells** as an expected-empty check, with any served value there.
