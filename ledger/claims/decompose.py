"""T6 decomposer (D-044 item 2; D15): one Claimify-style prompt, Sonnet 5.5 through the Batch API,
structured output, one completion per answer.

* The prompt is ONE tracked file (``decomposition.prompt_path``): the system text, then a
  ``=== USER MESSAGE TEMPLATE ===`` line, then the user template. Its SHA-256 over the file bytes
  must equal ``decomposition.prompt_sha256`` or nothing is built (``PromptNotFrozen``). The file is
  ``-text`` in .gitattributes, so its bytes are identical on every host.
* Requests carry the D-041 pins from ``generator`` (model, thinking, effort) and no sampling
  parameter (D-019); they go out only through the resumable Batch job ledger (D28).
* Code guards on every returned claim (a failing claim is DROPPED and recorded, never repaired):
  every numeric token occurs in the answer (``claims.numbers``, status 2026-10-14 (5)); the source
  sentence index is in range, and the claim inherits that sentence's citations; duplicates within
  an answer are removed (first kept). Abstentions are excluded before any request is built.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import anthropic
from pydantic import ValidationError

from ledger.baseline.match import collapse, normalize_numeric
from ledger.baseline.request import message_params
from ledger.baseline.schema import Answer, AnswerInvalid, parse_answer
from ledger.claims.numbers import missing_numbers
from ledger.claims.schema import ClaimRecord, Decomposition
from ledger.config import Config
from ledger.matrix.jobs import BatchClient, JobKey, JobLedger, RunSummary, run_seed

SEED = 1  # the decomposition is one cell at seed 1; it is not a matrix seed
TEMPLATE_MARKER = "\n=== USER MESSAGE TEMPLATE ===\n"
NORMAL_STOP = "end_turn"


class PromptNotFrozen(RuntimeError):
    pass


class DecompositionInvalid(ValueError):
    pass


# ---- the frozen prompt ------------------------------------------------------------------------


def prompt_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@dataclass(frozen=True)
class Prompt:
    system: str
    template: str
    sha256: str


def load_prompt(cfg: Config) -> Prompt:
    """The frozen prompt, or ``PromptNotFrozen`` (empty pin, or the file changed)."""
    path = Path(cfg.decomposition.prompt_path)
    got = prompt_sha256(path)
    pinned = cfg.decomposition.prompt_sha256
    if not pinned:
        raise PromptNotFrozen(f"decomposition.prompt_sha256 is empty; {path} hashes to {got}")
    if got != pinned:
        raise PromptNotFrozen(
            f"{path} hashes to {got}, not the pinned {pinned}: the prompt is frozen (D-044 item 2)"
        )
    text = path.read_bytes().decode("utf-8")
    if TEMPLATE_MARKER not in text:
        raise PromptNotFrozen(f"{path} has no user-template marker")
    system, template = text.split(TEMPLATE_MARKER, 1)
    return Prompt(system.strip(), template, got)


def user_message(template: str, question: str, sentences: Sequence[str]) -> str:
    body = "\n".join(f"[{i}] {s}" for i, s in enumerate(sentences))
    return template.replace("{question}", question).replace("{sentences}", body).rstrip("\n")


def decomposition_json_schema() -> dict[str, Any]:
    return anthropic.transform_schema(Decomposition)


def build_params(
    cfg: Config, prompt: Prompt, *, question: str, sentences: Sequence[str]
) -> dict[str, Any]:
    gen = cfg.generator
    body = message_params(
        gen.model,
        cfg.decomposition.max_tokens,
        gen.thinking,
        gen.effort,
        messages=[{"role": "user", "content": user_message(prompt.template, question, sentences)}],
    )
    body["system"] = prompt.system
    # merged into the dict that carries D-041's effort - never replacing it
    body["output_config"] = {
        **body["output_config"],
        "format": {"type": "json_schema", "schema": decomposition_json_schema()},
    }
    return body


def parse_decomposition(content: Sequence[Mapping[str, Any]]) -> Decomposition:
    text = "".join(b.get("text", "") for b in content if b.get("type") == "text")
    if not text.strip():
        raise DecompositionInvalid("no text block in the response")
    try:
        return Decomposition.model_validate(json.loads(text))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise DecompositionInvalid(str(exc)) from exc


# ---- inputs: run 1's non-abstaining draft answers (D-044 item 1) -------------------------------


@dataclass(frozen=True)
class AnswerItem:
    question_id: str
    stratum: str
    question: str
    answer: Answer

    @property
    def sentences(self) -> list[str]:
        return [s.text for s in self.answer.sentences]

    @property
    def text(self) -> str:
        return " ".join(self.sentences)


@dataclass
class InputSummary:
    items: list[AnswerItem] = field(default_factory=list)
    abstained: list[str] = field(default_factory=list)
    unusable: list[str] = field(default_factory=list)  # missing / errored / invalid / not end_turn


def input_path(cfg: Config) -> Path:
    return Path(cfg.paths.results_dir) / cfg.decomposition.input_cell / "1.jsonl"


def read_answers(cfg: Config, questions: Sequence[Mapping[str, Any]]) -> InputSummary:
    """Run 1 of the T5 Batch of record, draft questions only (controls and the supplement are not
    T6 input). Abstentions are excluded (item 2)."""
    have: dict[str, dict[str, Any]] = {}
    for ln in input_path(cfg).read_text(encoding="utf-8").splitlines():
        if ln.strip():
            rec = json.loads(ln)
            have[rec["question_id"]] = rec
    out = InputSummary()
    for q in sorted(questions, key=lambda q: q["question_id"]):
        if q.get("set") != "draft":
            continue
        qid = q["question_id"]
        rec = have.get(qid)
        message = ((rec or {}).get("payload") or {}).get("message") or {}
        if (
            rec is None
            or rec["result_type"] != "succeeded"
            or message.get("stop_reason") != (NORMAL_STOP)
        ):
            out.unusable.append(qid)
            continue
        try:
            answer = parse_answer(
                list(message.get("content") or []), output_mode=cfg.generator.output_mode
            )
        except AnswerInvalid:
            out.unusable.append(qid)
            continue
        if answer.abstained:
            out.abstained.append(qid)
            continue
        out.items.append(AnswerItem(qid, q["chunk_type"], q["question"], answer))
    return out


# ---- guards -------------------------------------------------------------------------------------


def dedup_key(text: str) -> str:
    return collapse(normalize_numeric(text)).strip().casefold()


def apply_guards(item: AnswerItem, dec: Decomposition) -> list[ClaimRecord]:
    """Every returned claim, kept or dropped (with the reason), in decomposer order."""
    out: list[ClaimRecord] = []
    seen: set[str] = set()
    kept_n = dropped_n = 0
    for c in dec.claims:
        reason, detail, citations = None, "", []
        if not c.text.strip():
            reason = "empty"
        elif not 0 <= c.source_sentence_idx < len(item.answer.sentences):
            reason = "sentence_index_out_of_range"
            detail = f"index {c.source_sentence_idx} of {len(item.answer.sentences)} sentences"
        else:
            citations = list(item.answer.sentences[c.source_sentence_idx].cited_chunk_ids)
            missing = missing_numbers(c.text, item.text)
            if missing:
                reason, detail = "number_not_in_answer", ", ".join(missing)
            elif dedup_key(c.text) in seen:
                reason = "duplicate"
        if reason is None:
            seen.add(dedup_key(c.text))
            kept_n += 1
            cid = f"{item.question_id}::c{kept_n:02d}"
        else:
            dropped_n += 1
            cid = f"{item.question_id}::x{dropped_n:02d}"
        out.append(
            ClaimRecord(
                claim_id=cid,
                question_id=item.question_id,
                stratum=item.stratum,
                text=c.text,
                source_sentence_idx=c.source_sentence_idx,
                qualifiers=c.qualifiers,
                citations=citations,
                kept=reason is None,
                drop_reason=reason,
                drop_detail=detail,
            )
        )
    return out


# ---- Batch: submit / collect --------------------------------------------------------------------


def make_build_request(
    cfg: Config, prompt: Prompt, items: Mapping[str, AnswerItem]
) -> Callable[[JobKey], dict[str, Any]]:
    def build(key: JobKey) -> dict[str, Any]:
        it = items[key.question_id]
        return build_params(cfg, prompt, question=it.question, sentences=it.sentences)

    return build


def submit_or_collect(
    cfg: Config,
    prompt: Prompt,
    items: Sequence[AnswerItem],
    client: BatchClient,
    *,
    ledger_path: Path,
) -> RunSummary:
    if not cfg.generator.use_batch:
        raise RuntimeError("generator.use_batch is false; the decomposer is Batch-only (D28)")
    by_id = {it.question_id: it for it in items}
    return run_seed(
        JobLedger(ledger_path),
        client,
        cells=[cfg.decomposition.cell],
        question_ids=sorted(by_id),
        seed=SEED,
        build_request=make_build_request(cfg, prompt, by_id),
        results_dir=cfg.paths.results_dir,
    )


def results_path(cfg: Config) -> Path:
    return Path(cfg.paths.results_dir) / cfg.decomposition.cell / f"{SEED}.jsonl"


@dataclass
class Collected:
    records: list[ClaimRecord] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)  # question_id -> why
    returned: dict[str, int] = field(default_factory=dict)
    usage: dict[str, dict[str, Any]] = field(default_factory=dict)
    content: dict[str, list[dict[str, Any]]] = field(default_factory=dict)


def collect(cfg: Config, items: Sequence[AnswerItem]) -> Collected:
    """Parse every collected result; an answer whose request failed has no claims and is listed
    in ``failed`` (one completion per answer: no retry)."""
    have: dict[str, dict[str, Any]] = {}
    path = results_path(cfg)
    if path.exists():
        for ln in path.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                rec = json.loads(ln)
                have[rec["question_id"]] = rec
    out = Collected()
    for it in items:
        rec = have.get(it.question_id)
        if rec is None:
            out.failed[it.question_id] = "no result"
            continue
        message = (rec.get("payload") or {}).get("message") or {}
        out.usage[it.question_id] = dict(message.get("usage") or {})
        out.content[it.question_id] = list(message.get("content") or [])
        if rec["result_type"] != "succeeded":
            out.failed[it.question_id] = rec["result_type"]
            continue
        if message.get("stop_reason") != NORMAL_STOP:
            out.failed[it.question_id] = f"stop_reason {message.get('stop_reason')}"
            continue
        try:
            dec = parse_decomposition(message.get("content") or [])
        except DecompositionInvalid as exc:
            out.failed[it.question_id] = f"invalid: {exc}"
            continue
        out.returned[it.question_id] = len(dec.claims)
        out.records.extend(apply_guards(it, dec))
    return out


def file_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def claims_manifest(cfg: Config, prompt: Prompt, items: Sequence[AnswerItem], got: Collected):
    reasons: dict[str, int] = {}
    for r in got.records:
        if not r.kept:
            reasons[r.drop_reason or "?"] = reasons.get(r.drop_reason or "?", 0) + 1
    return {
        "manifest": True,
        "prompt_path": Path(cfg.decomposition.prompt_path).as_posix(),
        "prompt_sha256": prompt.sha256,
        "model": cfg.generator.model,
        "thinking": cfg.generator.thinking,
        "effort": cfg.generator.effort,
        "max_tokens": cfg.decomposition.max_tokens,
        "input_cell": cfg.decomposition.input_cell,
        "input_sha256": file_sha256(input_path(cfg)),
        "results_sha256": file_sha256(results_path(cfg)),
        "answers": len(items),
        "failed": got.failed,
        "claims_returned": sum(got.returned.values()),
        "claims_kept": sum(r.kept for r in got.records),
        "dropped_by_reason": dict(sorted(reasons.items())),
    }


def write_claims(path: Path, manifest: Mapping[str, Any], records: Sequence[ClaimRecord]) -> None:
    lines = [json.dumps(dict(manifest), sort_keys=True, ensure_ascii=False)]
    lines += [
        json.dumps(r.model_dump(mode="json"), sort_keys=True, ensure_ascii=False) for r in records
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    tmp.replace(path)


def read_claims(path: Path) -> tuple[dict[str, Any], list[ClaimRecord]]:
    rows = [json.loads(ln) for ln in Path(path).read_text(encoding="utf-8").splitlines() if ln]
    if not rows or not rows[0].get("manifest"):
        raise ValueError(f"{path}: first line must be the decomposer's manifest")
    return rows[0], [ClaimRecord.model_validate(r) for r in rows[1:]]


def render_report(manifest: Mapping[str, Any], items: Sequence[AnswerItem], got: Collected) -> str:
    out = ["# T6 decomposition (D-044 item 2)", ""]
    out += [f"- {k}: `{v}`" for k, v in manifest.items() if k != "manifest"]
    out += [
        "",
        "| question | stratum | sentences | returned | kept | dropped |",
        "|---|---|---|---|---|---|",
    ]
    for it in items:
        rows = [r for r in got.records if r.question_id == it.question_id]
        status = got.failed.get(it.question_id)
        out.append(
            f"| {it.question_id} | {it.stratum} | {len(it.sentences)} | "
            f"{status or got.returned.get(it.question_id, 0)} | {sum(r.kept for r in rows)} | "
            f"{sum(not r.kept for r in rows)} |"
        )
    dropped = [r for r in got.records if not r.kept]
    out += ["", f"## Dropped claims ({len(dropped)})", ""]
    if dropped:
        out += ["| claim | reason | detail | text |", "|---|---|---|---|"]
        out += [
            f"| {r.claim_id} | {r.drop_reason} | {r.drop_detail} | {r.text.replace('|', '/')} |"
            for r in dropped
        ]
    else:
        out.append("None.")
    return "\n".join(out) + "\n"


# ---- tracing (D29: every LLM call emits a span) -------------------------------------------------


def trace_decompositions(
    cfg: Config, items: Sequence[AnswerItem], got: Collected, traced_path: Path
) -> int:
    """One LLM span per collected decomposition, once (a marker file remembers which). Batch
    usage arrives at collection, so spans are emitted then."""
    from ledger.tracing import otel

    done: set[str] = set()
    if traced_path.exists():
        done = {ln.strip() for ln in traced_path.read_text(encoding="utf-8").splitlines()}
    emitted = 0
    for it in items:
        qid = it.question_id
        if qid not in got.content or qid in done:
            continue
        with otel.run_span("decompose", {otel.RAG_QUESTION_ID: qid}):
            with otel.llm_span(
                "decompose",
                provider="anthropic",
                model_name=cfg.generator.model,
                invocation_parameters={
                    "max_tokens": cfg.decomposition.max_tokens,
                    "thinking": cfg.generator.thinking,
                    "effort": cfg.generator.effort,
                    "output_mode": "structured_output",
                    "batch": True,
                },
            ) as llm:
                otel.set_llm_result(
                    llm,
                    input_messages=[{"role": "user", "content": " ".join(it.sentences)}],
                    output_messages=[
                        {
                            "role": "assistant",
                            "content": json.dumps(got.content[qid], ensure_ascii=False),
                        }
                    ],
                    usage=got.usage.get(qid) or {},
                )
        traced_path.parent.mkdir(parents=True, exist_ok=True)
        with traced_path.open("a", encoding="utf-8") as fh:
            fh.write(qid + "\n")
        emitted += 1
    return emitted
