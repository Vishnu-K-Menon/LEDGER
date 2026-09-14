"""D-017 / D29 tests against an in-memory exporter. No phoenix, no network."""

import json

import pytest
from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import INVALID_SPAN, format_span_id, format_trace_id

from ledger.config import load_config
from ledger.tracing import otel

VERDICT = otel.VerdictRecord(
    claim_id="c1",
    label="SUPPORTED",
    score=0.91,
    evidence_ids=["doc::p3::tbl-1"],
    input_mode="concatenated",
    threshold=0.5,
    cited_support=True,
    verifier_model="bespoke-ai/Bespoke-MiniCheck-7B",
    verifier_revision="abc123",
)


@pytest.fixture
def exporter(base_config_path):
    exp = InMemorySpanExporter()
    otel.init_tracing(load_config(base_config_path), exporter=exp)
    yield exp
    otel.shutdown_tracing()


def _by_name(exporter, name):
    return next(s for s in exporter.get_finished_spans() if s.name == name)


def test_verdict_inline_on_open_verify_span(exporter):
    with otel.verify_span("c1") as span:
        otel.record_verdict(span, VERDICT)
        assert span.is_recording()
        live = dict(span.attributes)  # present before end()
    assert live["evaluations.0.evaluation.name"] == "claim_support"
    a = _by_name(exporter, "verify").attributes
    assert a[SpanAttributes.OPENINFERENCE_SPAN_KIND] == OpenInferenceSpanKindValues.TOOL.value
    assert a["tool.name"] == "verify"
    assert a["evaluations.0.evaluation.label"] == "SUPPORTED"
    assert a["evaluations.0.evaluation.score"] == pytest.approx(0.91)
    assert a["evaluations.0.evaluation.annotator_kind"] == "LLM"
    assert a["evaluations.0.evaluation.identifier"] == "bespoke-ai/Bespoke-MiniCheck-7B@abc123"
    assert json.loads(a["evaluations.0.evaluation.metadata"])["claim_id"] == "c1"


def test_posthoc_carrier_has_exactly_one_link(exporter):
    with otel.verify_span("c1") as span:
        target = otel.ids_of(span)
    carrier = otel.emit_posthoc_evaluation(
        target, {"name": "human_label", "label": "PARTIAL", "score": 0.5}, annotator_kind="HUMAN"
    )
    finished = next(s for s in exporter.get_finished_spans() if s.name == carrier.name)
    assert len(finished.links) == 1
    ctx = finished.links[0].context
    assert (format_trace_id(ctx.trace_id), format_span_id(ctx.span_id)) == target
    assert finished.parent is None  # root span: parentage never identifies the target
    a = finished.attributes
    assert a[SpanAttributes.OPENINFERENCE_SPAN_KIND] == OpenInferenceSpanKindValues.EVALUATOR.value
    assert a["evaluations.0.evaluation.annotator_kind"] == "HUMAN"
    assert a["evaluations.0.evaluation.label"] == "PARTIAL"


def test_record_verdict_noop_on_non_recording_span():
    """Tracing is never load-bearing: a no-op span must not raise."""
    otel.record_verdict(INVALID_SPAN, VERDICT)


def test_record_verdict_noop_on_ended_span(exporter):
    with otel.verify_span("c1") as span:
        pass
    otel.record_verdict(span, VERDICT)  # ended -> non-recording -> silent no-op


def test_record_verdict_rejects_non_span():
    with pytest.raises(TypeError):
        otel.record_verdict(object(), VERDICT)  # type: ignore[arg-type]


def test_posthoc_noop_when_tracing_disabled(base_config_path, tmp_path):
    override = tmp_path / "o.yaml"
    override.write_text("tracing:\n  enabled: false\n", encoding="utf-8")
    exp = InMemorySpanExporter()
    otel.init_tracing(load_config(base_config_path, override), exporter=exp)
    try:
        otel.emit_posthoc_evaluation(("0" * 31 + "1", "0" * 15 + "1"), {"name": "x", "score": 1.0})
        assert exp.get_finished_spans() == ()
    finally:
        otel.shutdown_tracing()


def test_llm_span_token_counts(exporter):
    with otel.llm_span("generate", provider="anthropic", model_name="claude-sonnet-5") as span:
        otel.set_llm_result(
            span,
            input_messages=[{"role": "user", "content": "q"}],
            output_messages=[{"role": "assistant", "content": "a"}],
            usage={"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 3},
        )
    a = _by_name(exporter, "generate").attributes
    assert a[SpanAttributes.LLM_TOKEN_COUNT_PROMPT] == 10
    assert a[SpanAttributes.LLM_TOKEN_COUNT_COMPLETION] == 5
    assert a[SpanAttributes.LLM_TOKEN_COUNT_TOTAL] == 15
    assert a[SpanAttributes.LLM_TOKEN_COUNT_PROMPT_DETAILS_CACHE_READ] == 3


def test_no_exporter_without_endpoint(base_config_path, monkeypatch):
    """D-014: with the env var unset, no OTLP exporter is attached and nothing errors."""
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    provider = otel.init_tracing(load_config(base_config_path))
    try:
        assert provider._active_span_processor._span_processors == ()
        with otel.verify_span("c1") as span:
            otel.record_verdict(span, VERDICT)
    finally:
        otel.shutdown_tracing()
