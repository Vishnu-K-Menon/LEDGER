# T5 output-mode investigation (D-043 item 5)

Written 2026-10-09 from the installed SDK source and Anthropic's documentation pages (read in the
build session). **No API call was made.** Facts are labelled: *SDK* = read from
`.venv/.../anthropic` 1.5.0, *docs* = the two doc pages named below, *derived* = my reading of how
they combine with D13 and A4, *unmeasured* = needs the dry run.

Docs read: `build-with-claude/structured-outputs`, `agents-and-tools/tool-use/strict-tool-use`.
The owner rules on the mode (status line on D-043); `generator.output_mode` stays empty until then.

## What anthropic 1.5.0 supports

| | `structured_output` | `strict_tool` |
|---|---|---|
| Sync path | *SDK* `messages.create(..., output_config={"effort": ..., "format": {"type": "json_schema", "schema": {...}}})`. `OutputConfigParam` has `effort` and `format`; `JSONOutputFormatParam` has `schema` and `type: "json_schema"`. | *SDK* `messages.create(..., tools=[{"name", "input_schema", "strict": True, ...}], tool_choice={"type": "auto"})`. `ToolParam.strict: bool`; `ToolChoiceAutoParam`. |
| Batch path | *SDK* `Request.params` is `MessageCreateParamsNonStreaming`, the same TypedDicts as sync. Not enforced at runtime (as with D-019), so the body shape is ours to get right. *docs* "Works with Batch processing". | Same body type. *docs* strict tool use "compiles ... using the same pipeline as structured outputs"; Batch is not mentioned on that page. *unmeasured* on Batch. |
| Helper | `anthropic.transform_schema(Answer)` (SDK `lib/_parse/_transform.py`): strips unsupported keywords into descriptions, sets `additionalProperties: false` on every object. Used by both modes. `messages.parse()` also exists but builds the request itself, so the Batch body is built by hand here. | Same schema, as the tool's `input_schema`. |
| Typing note | `ThinkingConfigParam` in 1.5.0 is `enabled | disabled | adaptive`; `{"type": "between_tools"}` (D-041) is not in the typed union. TypedDicts are not enforced at runtime and the 2026-10-09 live call accepted it. A type checker would flag it; nothing at runtime does. | same |

## What the docs say each guarantees

- **structured_output** (*docs*): constrained decoding; "valid JSON that matches your schema in the
  response's text content block". Exceptions the docs name: `stop_reason: "refusal"` (output may not
  match) and `stop_reason: "max_tokens"` (output may be incomplete). Enum casing is not guaranteed
  (the `Answer` schema has no enums).
- **strict_tool** (*docs*): "Tool `input` strictly follows the `input_schema`" and the tool name is
  valid, *when the model calls the tool*. Nothing in the docs makes the call itself happen:
  `tool_choice` `auto` leaves the model free to answer in prose, and forced tool use returns 400 on
  this model (D-041).

## Schema features

`Answer` uses: object, array, string, boolean; `required` on every property; `$defs`/`$ref` (for
`Sentence`); `additionalProperties: false`. It uses **none** of the unsupported features (recursion,
numeric or string constraints, `minItems` above 1, enums, unions). Optional parameters: 0 of the 24
allowed; union-typed parameters: 0 of 16. The cross-field rules (abstention form has no sentences;
a non-abstaining answer has at least one sentence, each with at least one citation) are not
expressible in the API's subset and live in pydantic validators. Both modes therefore reach the
same place on them: a schema-valid answer can still fail pydantic, and that is what A4 count 2
measures. Cited-ID membership (A4 count 3) is checked against the five supplied IDs outside the
schema in both modes.

## Interaction with D13's retry-once-then-fallback and with A4

| | `structured_output` | `strict_tool` |
|---|---|---|
| A4 count 1 (normal stop) | `end_turn`. Fails on `refusal` / `max_tokens`. Close to vacuous when nothing refuses. | `tool_use`. Also fails when the model answers in prose instead of calling the tool: a failure mode specific to this mode, and one that `tool_choice: auto` cannot rule out. |
| A4 count 2 (pydantic) | Cannot fail on syntax or types; fails on cross-field rules, refusals, truncation. | Same, plus any prose-only reply (no `tool_use` block to validate). |
| Retry (D13) | `retry_params` appends the assistant text and a user turn carrying the validation error. | Same, but when a tool call exists the retry must answer it with a `tool_result` (`is_error: true`) before continuing; when none exists it is a plain user turn. More protocol surface to get wrong. |
| Fallback | Sentence-split / `delete` (D13); `fallback=true` logged, counted as a decomposition error. | Same. |

## Token overhead (docs; not measured)

- structured_output: *docs* "Claude automatically receives an additional system prompt explaining
  the expected output format"; the page gives no size. The schema's own tokens are not billed as
  input text as far as the docs say, *unmeasured*.
- strict_tool: the tool definition (name, description, schema) is input; tool use also adds its own
  system-prompt overhead per the tool-use docs, size *unmeasured*.
- Neither is estimated here (CLAUDE.md: measured usage, not estimates). `scripts/t5_dry_run.py`
  prints `input_tokens` for the same question under both modes; the difference is the overhead.
- Both modes: *docs* grammar compilation adds latency on the first request per schema; cached 24 h.
  Changing `output_config.format` invalidates prompt caches (no caching is used here).

## Recommendation (the owner can overrule)

**`structured_output`.** (1) The answer is the response itself: no dependence on the model choosing
to call a tool, which `tool_choice: auto` cannot force on this model. (2) A4 then measures what it
is meant to (refusals, truncation, cross-field failures) rather than also measuring tool-call
compliance. (3) Retry is a plain turn. **Check at the dry run:** that `output_config` carrying both
`effort` and `format` is accepted together with `thinking: between_tools` on Sonnet 5.5; if the dry
run returns 400 for it, `strict_tool` is the fallback and the 400 text goes in the D-043 status
line.
