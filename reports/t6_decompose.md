# T6 decomposition (D-044 item 2)

- prompt_path: `ledger/claims/prompts/claimify_v1.md`
- prompt_sha256: `1c29c5a6dd2461405cb920e4d875c72d24ebe408321bc8faf711999e600093a4`
- model: `claude-sonnet-5-5`
- thinking: `between_tools`
- effort: `high`
- max_tokens: `4096`
- input_cell: `t5_baseline_r1`
- input_sha256: `a39b49b6f7b20f442958096b7d843cd4f37deffa77ec03c16d01e61bd8087599`
- results_sha256: `fc2907808b7d0ac289b301e832e59533908f54d7516250f27c48c494e7e12209`
- answers: `23`
- failed: `{}`
- claims_returned: `36`
- claims_kept: `34`
- dropped_by_reason: `{'number_not_in_answer': 2}`

| question | stratum | sentences | returned | kept | dropped |
|---|---|---|---|---|---|
| q001 | table | 1 | 1 | 1 | 0 |
| q002 | table | 1 | 2 | 2 | 0 |
| q004 | table | 1 | 1 | 1 | 0 |
| q005 | table | 1 | 1 | 1 | 0 |
| q006 | table | 1 | 1 | 1 | 0 |
| q007 | table | 1 | 1 | 1 | 0 |
| q008 | table | 1 | 1 | 1 | 0 |
| q009 | table | 1 | 1 | 1 | 0 |
| q011 | table | 1 | 1 | 1 | 0 |
| q012 | table | 1 | 1 | 1 | 0 |
| q013 | table | 1 | 1 | 1 | 0 |
| q014 | prose | 1 | 1 | 1 | 0 |
| q015 | prose | 1 | 2 | 2 | 0 |
| q016 | prose | 1 | 2 | 2 | 0 |
| q017 | prose | 1 | 2 | 2 | 0 |
| q018 | prose | 1 | 1 | 1 | 0 |
| q019 | prose | 1 | 2 | 2 | 0 |
| q020 | prose | 1 | 3 | 2 | 1 |
| q021 | prose | 2 | 2 | 2 | 0 |
| q022 | prose | 1 | 3 | 3 | 0 |
| q023 | prose | 1 | 2 | 2 | 0 |
| q024 | prose | 1 | 2 | 1 | 1 |
| q025 | prose | 1 | 2 | 2 | 0 |

## Dropped claims (2)

| claim | reason | detail | text |
|---|---|---|---|
| q020::x01 | number_not_in_answer | 2027 | In the Balances of Budget Authority for the Budget for Fiscal Year 2027, the FDIC holds two accounts that carry large balances. |
| q024::x01 | number_not_in_answer | 2023 | Under H.R. 3196, the Architect of the Capitol Appointment Act of 2023, the Architect of the Capitol would be appointed by a Congressional commission. |
