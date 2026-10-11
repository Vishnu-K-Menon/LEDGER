# T5 harness check

- model: `claude-sonnet-5-5`
- thinking / effort: `between_tools / high`
- questions sha256 (LF): `05bc4e4a8ea34cc6ff19882b5ea3598be9210d06f72ff4534b7410b790abc4c0`
- controls_accepted.json sha256 (LF): `d5feaa3a007af856ef1ac7ec47b82b2651919e00b98832f44ffc8f337973ab73`
- questions: `s001, c006, c007`

**PASS**: 3 of 3 calls accepted, ended `end_turn` and parsed (output mode `structured_output`; D-043 status 2026-10-10, item 5).

| question | set | accepted | stop_reason | parse | abstained | cited ids ⊆ supplied | input | output | thinking | pass |
|---|---|---|---|---|---|---|---|---|---|---|
| s001 | supplement | True | end_turn | ok | False | True | 2426 | 117 | 0 | True |
| c006 | control_candidate | True | end_turn | ok | True | True | 1657 | 79 | 0 | True |
| c007 | control_candidate | True | end_turn | ok | True | True | 5331 | 71 | 0 | True |

Cited-ID and abstention columns are informational, not part of the pass rule.
