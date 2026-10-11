# T5 verifier probe

Harness probe for T6 (D-003, D-004, D-012). **No scoring decision is made here**; no vLLM environment; bf16 transformers, one verifier resident at a time.

## Environment

- torch: `2.14.0+cu130`
- transformers: `5.17.0`
- gpu: `NVIDIA L40S`
- claims: `16 (4 per label x context cell, 4 questions)`
- claim form: `mechanical: The answer to the question "<q>" is <gold answer>. (altered = last digit +1); this tests digit sensitivity, not natural claims`
- minicheck pinned: `Liyan06/MiniCheck@b58b9fa69acbd1015ec970fa65dd752413a053d2`
- minicheck model: `bespokelabs/Bespoke-MiniCheck-7B@1ed7786bcda3fa1dc35f7c4ed9e3f36b785d33b8`
- granite model: `ibm-granite/granite-guardian-3.3-8b@b3421eda4ba6fc9f9a71121d7e62de08827469a4`

## Pinned sources (templates and examples are read from these, never from memory)

| role | repo | file | revision / commit | sha256 of the fetched file |
|---|---|---|---|---|
| MiniCheck system/user prompt | Liyan06/MiniCheck | `minicheck/utils.py` | `b58b9fa69acbd1015ec970fa65dd752413a053d2` | `d18d28c6ddc0a38d4186841304f3f164b72942a91fe3e13664b0965cba2c2d65` |
| MiniCheck apply_chat_template + P(yes) rule | Liyan06/MiniCheck | `minicheck/inference.py` | `b58b9fa69acbd1015ec970fa65dd752413a053d2` | `325292ec98f0e0902ada035d0e0d0395017082bd1b12a7a8e63e2d15df012d5a` |
| MiniCheck README example + expected numbers | Liyan06/MiniCheck | `README.md` | `b58b9fa69acbd1015ec970fa65dd752413a053d2` | `0e93835c8414847d0b349ee7830537e00d45e5d06ba55fbb6254fe14d4343776` |
| Bespoke-MiniCheck-7B model card (cross-check of the numbers) | bespokelabs/Bespoke-MiniCheck-7B | `README.md` | `1ed7786bcda3fa1dc35f7c4ed9e3f36b785d33b8` | `4fb6d554a2a3467f45666d7922ea7096e642b8c9e2e8ac0da96fd03efcb901ae` |
| Granite Guardian 3.3 model card (call shape, polarity, score parsing) | ibm-granite/granite-guardian-3.3-8b | `README.md` | `b3421eda4ba6fc9f9a71121d7e62de08827469a4` | `5b55df02a890c54dd1dc910b337f44ebced4416c14329663748be4f8fb5643bc` |

## Bespoke-MiniCheck-7B

README example (expected [0.9840446675150499, 0.010986349594852094]): got [0, 0] -> **NOT REPRODUCED** (tolerance +/- 0.02)

| question | label | context chunks | P(yes) | predicted supported | correct |
|---|---|---|---|---|---|
| q001 | supported | 1 | 0.000 | False | False |
| q001 | supported | 5 | 0.000 | False | False |
| q001 | altered | 1 | 0.000 | False | True |
| q001 | altered | 5 | 0.000 | False | True |
| q002 | supported | 1 | 0.000 | False | False |
| q002 | supported | 5 | 0.000 | False | False |
| q002 | altered | 1 | 0.000 | False | True |
| q002 | altered | 5 | 0.000 | False | True |
| q003 | supported | 1 | 0.000 | False | False |
| q003 | supported | 5 | 0.000 | False | False |
| q003 | altered | 1 | 0.000 | False | True |
| q003 | altered | 5 | 0.000 | False | True |
| q004 | supported | 1 | 0.000 | False | False |
| q004 | supported | 5 | 0.000 | False | False |
| q004 | altered | 1 | 0.000 | False | True |
| q004 | altered | 5 | 0.000 | False | True |

| label | context chunks | correct |
|---|---|---|
| altered | 1 | 4/4 |
| altered | 5 | 4/4 |
| supported | 1 | 0/4 |
| supported | 5 | 0/4 |

## Granite Guardian 3.3 8B

Template: `tokenizer.apply_chat_template([{'role': 'assistant', 'content': claim}], guardian_config={'criteria_id': 'groundedness'}, documents=[{'doc_id': '0', 'text': doc}], think=False, tokenize=False, add_generation_prompt=True)` (README at the pinned revision, Example 3 with think=False as in its Examples 1-2). Polarity per the card: `yes` = ungrounded, `no` = grounded.

| question | label | context chunks | raw output | parsed | predicted supported | correct |
|---|---|---|---|---|---|---|
| q001 | supported | 1 | `<think>
</think>
<score> no </score>` | no | True | True |
| q001 | supported | 5 | `<think>
</think>
<score> no </score>` | no | True | True |
| q001 | altered | 1 | `<think>
</think>
<score> yes </score>` | yes | False | True |
| q001 | altered | 5 | `<think>
</think>
<score> yes </score>` | yes | False | True |
| q002 | supported | 1 | `<think>
</think>
<score> no </score>` | no | True | True |
| q002 | supported | 5 | `<think>
</think>
<score> no </score>` | no | True | True |
| q002 | altered | 1 | `<think>
</think>
<score> yes </score>` | yes | False | True |
| q002 | altered | 5 | `<think>
</think>
<score> yes </score>` | yes | False | True |
| q003 | supported | 1 | `<think>
</think>
<score> no </score>` | no | True | True |
| q003 | supported | 5 | `<think>
</think>
<score> no </score>` | no | True | True |
| q003 | altered | 1 | `<think>
</think>
<score> yes </score>` | yes | False | True |
| q003 | altered | 5 | `<think>
</think>
<score> yes </score>` | yes | False | True |
| q004 | supported | 1 | `<think>
</think>
<score> no </score>` | no | True | True |
| q004 | supported | 5 | `<think>
</think>
<score> no </score>` | no | True | True |
| q004 | altered | 1 | `<think>
</think>
<score> yes </score>` | yes | False | True |
| q004 | altered | 5 | `<think>
</think>
<score> yes </score>` | yes | False | True |

| label | context chunks | correct |
|---|---|---|
| altered | 1 | 4/4 |
| altered | 5 | 4/4 |
| supported | 1 | 4/4 |
| supported | 5 | 4/4 |
