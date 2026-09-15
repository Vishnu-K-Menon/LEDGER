"""D30 cost path, D-019 wire body, and D-022 record types — checked on the producer side."""

import importlib.util
import json
from pathlib import Path

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from ledger.config import load_config
from ledger.tracing import otel

USAGE = {"input_tokens": 1_000_000, "output_tokens": 1_000_000}


def _probe_module(repo_root: Path):
    spec = importlib.util.spec_from_file_location("a5_probe", repo_root / "scripts" / "a5_probe.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_batch_selects_batch_rates(base_config_path):
    """batch=True must use batch_*_per_mtok; sync rates would double every D26 cost figure."""
    gen = load_config(base_config_path).generator
    p = gen.pricing_usd_per_mtok
    assert gen.cost_usd(USAGE, batch=True) == pytest.approx(p.batch_input + p.batch_output)
    assert gen.cost_usd(USAGE, batch=False) == pytest.approx(p.input + p.output)
    assert gen.cost_usd(USAGE, batch=True) < gen.cost_usd(USAGE, batch=False)


def test_message_body_has_no_sampling_keys(repo_root):
    """D-019: the body sent on both the sync and Batch paths carries no sampling key."""
    probe = _probe_module(repo_root)
    body = probe.message_params("claude-sonnet-5", 64)
    assert not ({"temperature", "top_p", "top_k"} & set(body))
    assert set(body) == {"model", "max_tokens", "messages"}


def test_batch_request_on_the_wire_has_no_sampling_keys(repo_root):
    """Drive _call_batch with a fake client and inspect what reaches batches.create."""
    probe = _probe_module(repo_root)
    sent = {}

    class _Msg:
        content = []

    class _Result:
        custom_id = "a5-probe"

        class result:
            type = "succeeded"
            message = _Msg()

    class _Batches:
        def create(self, requests):
            sent["requests"] = requests

            class _B:
                id = "b1"

            return _B()

        def retrieve(self, _id):
            class _S:
                processing_status = "ended"

            return _S()

        def results(self, _id):
            return [_Result()]

    class _Client:
        class messages:
            batches = _Batches()

    probe._call_batch(_Client(), "claude-sonnet-5", 64)
    (req,) = sent["requests"]
    assert req["custom_id"] == "a5-probe"
    assert not ({"temperature", "top_p", "top_k"} & set(req["params"]))


@pytest.fixture
def exporter(base_config_path):
    exp = InMemorySpanExporter()
    otel.init_tracing(load_config(base_config_path), exporter=exp)
    yield exp
    otel.shutdown_tracing()


def test_cost_lands_on_root_query_span(exporter, base_config_path):
    """D30: rag.cost_usd comes from usage x config price and sits on the AGENT root span."""
    gen = load_config(base_config_path).generator
    usage = {"input_tokens": 36, "output_tokens": 6}
    cost = gen.cost_usd(usage, batch=False)
    with otel.query_span("q", question_id="q1", arm="none", seed=1) as root:
        otel.set_query_result(root, iterations=0, stop_reason="probe", cost_usd=cost)
    (span,) = exporter.get_finished_spans()
    assert span.parent is None
    assert span.attributes[otel.RAG_COST_USD] == pytest.approx(cost)
    assert span.attributes[otel.RAG_RECORD_TYPE] == "query"


def test_verdict_metadata_is_json_string_on_the_wire(exporter):
    """OpenInference: evaluation.metadata is a JSON-serialized STRING; OTLP cannot carry objects."""
    verdict = otel.VerdictRecord(
        claim_id="c1",
        label="UNSUPPORTED",
        score=0.2,
        evidence_ids=[],
        input_mode="per_chunk_max",
        threshold=0.5,
        cited_support=False,
        verifier_model="m",
        verifier_revision="r",
    )
    with otel.verify_span("c1") as span:
        otel.record_verdict(span, verdict)
    (finished,) = exporter.get_finished_spans()
    meta = finished.attributes["evaluations.0.evaluation.metadata"]
    assert isinstance(meta, str)
    assert json.loads(meta) == {
        "claim_id": "c1",
        "input_mode": "per_chunk_max",
        "threshold": 0.5,
        "cited_support": False,
    }
    # explanation is a JSON string too (evidence_ids list), and every value is an OTLP scalar
    assert isinstance(finished.attributes["evaluations.0.evaluation.explanation"], str)
    assert all(isinstance(v, (str, bool, int, float)) for v in finished.attributes.values())


@pytest.mark.parametrize(
    ("kind", "record_type"), [("HUMAN", "human_label"), ("CODE", "code_label")]
)
def test_carrier_record_type(exporter, kind, record_type):
    """D-022: carriers are filterable out of the root-trace list by rag.record_type."""
    with otel.verify_span("c1") as span:
        target = otel.ids_of(span)
    otel.emit_posthoc_evaluation(target, {"name": "x", "label": "SUPPORTED"}, annotator_kind=kind)
    carrier = next(s for s in exporter.get_finished_spans() if s.name == "evaluation/x")
    assert carrier.parent is None
    assert carrier.attributes[otel.RAG_RECORD_TYPE] == record_type
    assert carrier.attributes["evaluations.0.evaluation.annotator_kind"] == kind
