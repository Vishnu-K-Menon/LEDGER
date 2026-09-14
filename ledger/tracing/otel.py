"""OpenInference instrumentation over OTLP — the one module behind which the convention set is
swappable (D29 as revised by D-014 and D-017).

* Endpoint: ``OTEL_EXPORTER_OTLP_ENDPOINT`` (headers: ``OTEL_EXPORTER_OTLP_HEADERS``), read by the
  OTLP exporter itself. Never hardcoded. Unset -> spans are created but nothing is exported.
* Attribute names: OpenInference ``llm.*`` etc. from the pinned
  ``openinference-semantic-conventions`` (D-018) — not ``gen_ai.*``.
* Verifier verdicts are written **inline** on the open verify span as ``evaluations.0.evaluation.*``
  (``record_verdict``). Human labels and re-scoring are **post-hoc** ``EVALUATOR`` carrier spans
  with exactly one Span Link to the target (``emit_posthoc_evaluation``). D-017.
* Tracing is never load-bearing: every helper is a no-op on a non-recording span, so
  ``tracing.enabled: false`` or a no-op provider cannot break a verify call.
* Nothing here imports ``phoenix`` (enforced by tests/test_guards.py).
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from typing import Any, Literal

from openinference.instrumentation import get_evaluation_attributes
from openinference.semconv.resource import ResourceAttributes
from openinference.semconv.trace import (
    DocumentAttributes,
    MessageAttributes,
    OpenInferenceAnnotatorKindValues,
    OpenInferenceMimeTypeValues,
    OpenInferenceSpanKindValues,
    RerankerAttributes,
    SpanAttributes,
    ToolAttributes,
)
from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor, SpanExporter
from opentelemetry.trace import Link, Span, SpanContext, SpanKind, TraceFlags
from pydantic import BaseModel, ConfigDict

from ledger.config import Config

log = logging.getLogger(__name__)

ENDPOINT_ENV = "OTEL_EXPORTER_OTLP_ENDPOINT"
TRACER_NAME = "ledger"

# Project-specific attributes (the ``rag.*`` namespace from D29). Not OpenInference keys.
RAG_QUESTION_ID = "rag.question_id"
RAG_ARM = "rag.arm"
RAG_SEED = "rag.seed"
RAG_ITER = "rag.iter"
RAG_STOP_REASON = "rag.stop_reason"
RAG_COST_USD = "rag.cost_usd"
RAG_CLAIM_ID = "rag.claim_id"

VERDICT_EVALUATION_NAME = "claim_support"

_provider: TracerProvider | None = None


# ---- setup ----------------------------------------------------------------------------------


def init_tracing(cfg: Config, *, exporter: SpanExporter | None = None) -> TracerProvider:
    """Create and register the global ``TracerProvider``.

    ``exporter`` overrides the OTLP exporter (tests pass an ``InMemorySpanExporter``). Otherwise
    the OTLP/HTTP exporter is attached only when ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set; the
    exporter reads the endpoint and ``OTEL_EXPORTER_OTLP_HEADERS`` from the environment itself
    (D-014: no endpoint in code or config).
    """
    global _provider
    resource = Resource.create(
        {
            SERVICE_NAME: cfg.tracing.service_name,
            ResourceAttributes.PROJECT_NAME: cfg.tracing.project_name,
        }
    )
    provider = TracerProvider(resource=resource)
    if not cfg.tracing.enabled:
        log.warning("tracing.enabled is false: spans are created but not exported")
    elif exporter is not None:
        provider.add_span_processor(SimpleSpanProcessor(exporter))
    elif os.environ.get(ENDPOINT_ENV):
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        log.info("OTLP exporter attached (endpoint from %s)", ENDPOINT_ENV)
    else:
        log.warning("%s is not set: spans are created but not exported", ENDPOINT_ENV)
    # The OTel global can be set only once per process; our own handle is what ``tracer()`` uses,
    # so re-initialising (tests, notebooks) always takes effect.
    trace.set_tracer_provider(provider)
    _provider = provider
    return provider


def shutdown_tracing() -> None:
    """Flush and shut down the provider created by ``init_tracing`` (call before exit)."""
    global _provider
    if _provider is not None:
        _provider.force_flush()
        _provider.shutdown()
        _provider = None


def tracer() -> trace.Tracer:
    if _provider is not None:
        return _provider.get_tracer(TRACER_NAME)
    return trace.get_tracer(TRACER_NAME)


def ids_of(span: Span) -> tuple[str, str]:
    """``(trace_id, span_id)`` as 32/16-char hex — what the ledger row stores (D-017)."""
    ctx = span.get_span_context()
    return trace.format_trace_id(ctx.trace_id), trace.format_span_id(ctx.span_id)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _kind_attrs(kind: OpenInferenceSpanKindValues) -> dict[str, str]:
    return {SpanAttributes.OPENINFERENCE_SPAN_KIND: kind.value}


# ---- span plan (D29) ------------------------------------------------------------------------


@contextmanager
def query_span(question: str, *, question_id: str, arm: str, seed: int) -> Iterator[Span]:
    """Root span per query, kind AGENT."""
    attrs: dict[str, Any] = {
        **_kind_attrs(OpenInferenceSpanKindValues.AGENT),
        SpanAttributes.INPUT_VALUE: question,
        RAG_QUESTION_ID: question_id,
        RAG_ARM: arm,
        RAG_SEED: seed,
    }
    with tracer().start_as_current_span("query", attributes=attrs) as span:
        yield span


def set_query_result(
    span: Span, *, iterations: int, stop_reason: str, cost_usd: float, answer: str | None = None
) -> None:
    if not span.is_recording():
        return
    span.set_attributes(
        {RAG_ITER: iterations, RAG_STOP_REASON: stop_reason, RAG_COST_USD: cost_usd}
    )
    if answer is not None:
        span.set_attribute(SpanAttributes.OUTPUT_VALUE, answer)


@contextmanager
def llm_span(
    name: Literal["generate", "decompose", "rewrite"] | str,
    *,
    provider: str,
    model_name: str,
    invocation_parameters: Mapping[str, Any] | None = None,
) -> Iterator[Span]:
    """One LLM-kind span per generate / decompose / rewrite call."""
    attrs: dict[str, Any] = {
        **_kind_attrs(OpenInferenceSpanKindValues.LLM),
        SpanAttributes.LLM_PROVIDER: provider,
        SpanAttributes.LLM_MODEL_NAME: model_name,
    }
    if invocation_parameters:
        attrs[SpanAttributes.LLM_INVOCATION_PARAMETERS] = _json(dict(invocation_parameters))
    with tracer().start_as_current_span(name, attributes=attrs) as span:
        yield span


def set_llm_result(
    span: Span,
    *,
    input_messages: Sequence[Mapping[str, str]],
    output_messages: Sequence[Mapping[str, str]],
    usage: Mapping[str, int | None],
) -> None:
    """Record messages and token counts. ``usage`` keys: ``input_tokens``, ``output_tokens``,
    optional ``cache_read_input_tokens`` / ``cache_creation_input_tokens`` — the API's usage
    fields, never estimates (D31)."""
    if not span.is_recording():
        return
    attrs: dict[str, Any] = {}
    for prefix, msgs in (
        (SpanAttributes.LLM_INPUT_MESSAGES, input_messages),
        (SpanAttributes.LLM_OUTPUT_MESSAGES, output_messages),
    ):
        for i, m in enumerate(msgs):
            attrs[f"{prefix}.{i}.{MessageAttributes.MESSAGE_ROLE}"] = m["role"]
            attrs[f"{prefix}.{i}.{MessageAttributes.MESSAGE_CONTENT}"] = m["content"]
    prompt = usage.get("input_tokens")
    completion = usage.get("output_tokens")
    if prompt is not None:
        attrs[SpanAttributes.LLM_TOKEN_COUNT_PROMPT] = prompt
    if completion is not None:
        attrs[SpanAttributes.LLM_TOKEN_COUNT_COMPLETION] = completion
    if prompt is not None and completion is not None:
        attrs[SpanAttributes.LLM_TOKEN_COUNT_TOTAL] = prompt + completion
    cache_read = usage.get("cache_read_input_tokens")
    cache_write = usage.get("cache_creation_input_tokens")
    if cache_read is not None:
        attrs[SpanAttributes.LLM_TOKEN_COUNT_PROMPT_DETAILS_CACHE_READ] = cache_read
    if cache_write is not None:
        attrs[SpanAttributes.LLM_TOKEN_COUNT_PROMPT_DETAILS_CACHE_WRITE] = cache_write
    span.set_attributes(attrs)


@contextmanager
def retriever_span(query: str) -> Iterator[Span]:
    """One RETRIEVER-kind span per ``retrieve``."""
    attrs = {
        **_kind_attrs(OpenInferenceSpanKindValues.RETRIEVER),
        SpanAttributes.INPUT_VALUE: query,
    }
    with tracer().start_as_current_span("retrieve", attributes=attrs) as span:
        yield span


def set_retrieved_documents(
    span: Span,
    docs: Sequence[Mapping[str, Any]],
    *,
    prefix: str = SpanAttributes.RETRIEVAL_DOCUMENTS,
) -> None:
    """``docs`` items carry ``id`` and ``score`` (chunk IDs are the citation unit, D-005)."""
    if not span.is_recording():
        return
    attrs: dict[str, Any] = {}
    for i, d in enumerate(docs):
        attrs[f"{prefix}.{i}.{DocumentAttributes.DOCUMENT_ID}"] = str(d["id"])
        if d.get("score") is not None:
            attrs[f"{prefix}.{i}.{DocumentAttributes.DOCUMENT_SCORE}"] = float(d["score"])
        if d.get("content") is not None:
            attrs[f"{prefix}.{i}.{DocumentAttributes.DOCUMENT_CONTENT}"] = str(d["content"])
    span.set_attributes(attrs)


@contextmanager
def reranker_span(query: str, *, top_k: int, model_name: str) -> Iterator[Span]:
    """RERANKER-kind span following each retrieve; set output ids with
    ``set_retrieved_documents(span, docs, prefix=RerankerAttributes.RERANKER_OUTPUT_DOCUMENTS)``."""
    attrs = {
        **_kind_attrs(OpenInferenceSpanKindValues.RERANKER),
        RerankerAttributes.RERANKER_QUERY: query,
        RerankerAttributes.RERANKER_TOP_K: top_k,
        RerankerAttributes.RERANKER_MODEL_NAME: model_name,
    }
    with tracer().start_as_current_span("rerank", attributes=attrs) as span:
        yield span


@contextmanager
def verify_span(claim_id: str) -> Iterator[Span]:
    """One TOOL-kind span per verify call; the verdict goes inline via ``record_verdict``."""
    attrs = {
        **_kind_attrs(OpenInferenceSpanKindValues.TOOL),
        ToolAttributes.TOOL_NAME: "verify",
        RAG_CLAIM_ID: claim_id,
    }
    with tracer().start_as_current_span("verify", attributes=attrs) as span:
        yield span


# ---- evaluation records (D-017) -------------------------------------------------------------


class VerdictRecord(BaseModel):
    """What ``record_verdict`` writes — the D-017 item-1 payload. The pipeline ``Verdict`` schema
    (D13, T9) converts to this; tracing does not import pipeline schemas."""

    model_config = ConfigDict(extra="forbid")

    claim_id: str
    label: Literal["SUPPORTED", "UNSUPPORTED"]
    score: float
    evidence_ids: list[str]
    input_mode: Literal["concatenated", "per_chunk_max"]
    threshold: float
    cited_support: bool
    verifier_model: str
    verifier_revision: str


def record_verdict(span: Span, verdict: VerdictRecord) -> None:
    """Write the verdict **inline** on the open verify span as ``evaluations.0.evaluation.*``.

    No-op on a non-recording span — disabled tracing, a no-op provider, or an already-ended span
    (ended spans are immutable; use ``emit_posthoc_evaluation`` for those). Tracing must never be
    load-bearing for a verify call. Raises ``TypeError`` only when ``span`` is not a span.
    """
    if not isinstance(span, Span):
        raise TypeError(f"record_verdict expects an OpenTelemetry Span, got {type(span).__name__}")
    if not span.is_recording():
        return
    span.set_attributes(
        get_evaluation_attributes(
            evaluations=[
                {
                    "name": VERDICT_EVALUATION_NAME,
                    "label": verdict.label,
                    "score": verdict.score,
                    "explanation": _json(verdict.evidence_ids),
                    "annotator_kind": OpenInferenceAnnotatorKindValues.LLM.value,
                    "identifier": f"{verdict.verifier_model}@{verdict.verifier_revision}",
                    "metadata": {
                        "claim_id": verdict.claim_id,
                        "input_mode": verdict.input_mode,
                        "threshold": verdict.threshold,
                        "cited_support": verdict.cited_support,
                    },
                }
            ],
            scope="span",
        )
    )
    span.set_attribute(SpanAttributes.OUTPUT_VALUE, verdict.model_dump_json())
    span.set_attribute(SpanAttributes.OUTPUT_MIME_TYPE, OpenInferenceMimeTypeValues.JSON.value)


def emit_posthoc_evaluation(
    target: tuple[str, str],
    annotation: Mapping[str, Any],
    *,
    annotator_kind: Literal["HUMAN", "CODE"] = "HUMAN",
) -> Span:
    """Emit one ``EVALUATOR`` carrier span with **exactly one Span Link** to ``target``.

    ``target`` is ``(trace_id_hex, span_id_hex)`` as stored on the ledger row. ``annotation`` has
    ``name`` plus at least one of ``score`` / ``label`` / ``explanation``, and optional
    ``identifier`` / ``metadata``. The carrier is a root span: parentage must never identify the
    target (D-017). Returns the (ended) span; on a non-recording provider it is a no-op span.
    """
    trace_id_hex, span_id_hex = target
    if not isinstance(annotation, Mapping) or not isinstance(annotation.get("name"), str):
        raise TypeError("annotation must be a mapping with a string 'name'")
    link = Link(
        SpanContext(
            trace_id=int(trace_id_hex, 16),
            span_id=int(span_id_hex, 16),
            is_remote=True,
            trace_flags=TraceFlags(TraceFlags.SAMPLED),
        )
    )
    payload = {
        k: annotation[k]
        for k in ("name", "score", "label", "explanation", "identifier", "metadata")
        if annotation.get(k) is not None
    }
    payload["annotator_kind"] = OpenInferenceAnnotatorKindValues(annotator_kind).value
    span = tracer().start_span(
        f"evaluation/{annotation['name']}",
        context=otel_context.Context(),  # explicit empty context -> root span, never a child
        kind=SpanKind.INTERNAL,
        links=[link],
        attributes={
            **_kind_attrs(OpenInferenceSpanKindValues.EVALUATOR),
            **get_evaluation_attributes(evaluations=[payload], scope="span"),
        },
    )
    span.end()
    return span
