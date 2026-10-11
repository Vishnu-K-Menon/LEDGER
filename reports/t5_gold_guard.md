# T5 gold guard

- questions sha256 (LF): `05bc4e4a8ea34cc6ff19882b5ea3598be9210d06f72ff4534b7410b790abc4c0`
- matcher: `ledger/baseline/match.py::gold_in_text` (the function that scores answers)

**PASS**: 26 of 26 golds occur in their own gold chunk with at least one occurrence that is not part of a longer number.

- q001 (number) `967` in `govinfo-BUDGET-2026-DOD::p39::tbl-175::s0`: ok
- q002 (number) `14.79` in `govinfo-BUDGET-2027-FCS::p97::tbl-83::s8`: ok
- q003 (number) `193.7` in `eia-pdf-steo_full::p49::tbl-21::s17`: ok
- q004 (number) `1,684` in `govinfo-BUDGET-2026-DOD::p35::tbl-152::s1`: ok
- q005 (number) `–106.3` in `govinfo-ERP-2026-table19::p2::tbl-1::s20`: ok
- q006 (number) `84,804` in `govinfo-BUDGET-2026-DOD::p55::tbl-257::s3`: ok
- q007 (number) `1.128` in `eia-pdf-steo_full::p51::tbl-23::s5`: ok
- q008 (number) `28,485` in `govinfo-BUDGET-2026-DOD::p6::tbl-4::s0`: ok
- q009 (number) `348.1` in `govinfo-ERP-2026-table19::p1::tbl-0::s0`: ok
- q010 (number) `177` in `govinfo-BUDGET-2026-DOD::p40::tbl-177::s2`: ok
- q011 (number) `7,202` in `govinfo-BUDGET-2026-DOD::p34::tbl-149::s0`: ok
- q012 (number) `5.25` in `govinfo-ERP-2026-table42::p1::tbl-0::s9`: ok
- q013 (number) `-30,637` in `govinfo-BUDGET-2027-PER::p26::tbl-6::s2`: ok
- q014 (short_phrase) `one out  of  every  five  American  professors` in `govinfo-CRPT-118hrpt468::p14::txt-411::s0`: ok
- q015 (short_phrase) `more than 90 days` in `govinfo-BUDGET-2027-PER::p71::txt-1065::s0`: ok
- q016 (number) `$194,653 million` in `govinfo-BUDGET-2026-DOD::p5::txt-27::s0`: ok
- q017 (short_phrase) `section  2339A of title 18, United States Code` in `govinfo-CRPT-118hrpt468::p34::txt-904::s0`: ok
- q018 (short_phrase) `12th` in `govinfo-ERP-2026-table22::p2::txt-13::s0`: ok
- q019 (short_phrase) `five major lines of effort` in `govinfo-BUDGET-2025-CLIMATE::p72::txt-369::s0`: ok
- q020 (short_phrase) `the Deposit Insurance Fund (DIF) and the FSLIC Resolution Fund (FRF)` in `govinfo-BUDGET-2027-BALANCES::p6::txt-36::s0`: ok
- q021 (short_phrase) `only to the extent they have been granted budget authority` in `govinfo-BUDGET-2027-PER::p61::txt-879::s0`: ok
- q022 (short_phrase) `a  brochure, a workshop, or training` in `govinfo-CRPT-118hrpt468::p49::txt-1279::s0`: ok
- q023 (short_phrase) `Multiple Award Schedule program` in `cbo-61099::p3::txt-68::s0`: ok
- q024 (short_phrase) `a Congressional commission` in `cbo-59853::p1::txt-6::s0`: ok
- q025 (short_phrase) `§ 4` in `govinfo-CRPT-118hrpt468::p58::txt-1489::s0`: ok
- s001 (number) `$1 million` in `cbo-61720::p3::tbl-1::s0`: ok
