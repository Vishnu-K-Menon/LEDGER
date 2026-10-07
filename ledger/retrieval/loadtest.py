"""``ledger loadtest`` — A8 (D-012; how it is run: D-012 status 2026-10-07).

Embedder + reranker + one verifier candidate resident on one GPU, all bf16, loaded in-process
with transformers (no vLLM: it reserves most of the GPU by default, so its reading would not be a
co-residency measurement). One embed, one rerank and one verify call per candidate, on an input of
``retrieval.k_final`` chunks at the corpus maximum length. The measured number is device memory in
use at the peak of the verify call, read from nvidia-smi, against ``loadtest.limit_gib``.

Outcomes per candidate: PASS / FAIL (peak over the limit — reported, D-012's fallback is not
applied here) / GATED (401/403 on a repo that resolves; no HF token exists in this project) /
NOT LOADED (any other failure, with the error). Only PASS counts as a pass; embedder + reranker
alone is not an A8 result.

The verify call is a LOAD TEST. Its score is not a validated MiniCheck or Granite Guardian score:
the prompt below is generic, not either model's published template.
"""

from __future__ import annotations

import gc
import json
import os
import platform
import subprocess
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ledger.config import Config
from ledger.retrieval.index import read_chunks

GIB = 1024  # nvidia-smi reports MiB


def nvidia_smi_used_mib() -> int:
    """Device memory in use, GPU 0, from nvidia-smi (raises if it cannot be read: a load test
    without the device reading is not an A8 result)."""
    out = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits", "-i", "0"],
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
    ).stdout
    return int(out.strip().splitlines()[0])


class PeakSampler:
    """Polls nvidia-smi on a thread; ``peak`` is the maximum sample (plus a final reading)."""

    def __init__(self, interval: float):
        self.interval = interval
        self.peak = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.peak = max(self.peak, nvidia_smi_used_mib())
            except (OSError, subprocess.SubprocessError, ValueError):
                pass
            self._stop.wait(self.interval)

    def __enter__(self) -> PeakSampler:
        self.peak = nvidia_smi_used_mib()
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        self._thread.join()
        self.peak = max(self.peak, nvidia_smi_used_mib())


@dataclass
class CandidateResult:
    repo_id: str
    revision: str
    status: str = "NOT LOADED"  # PASS | FAIL | GATED | NOT LOADED
    detail: str = ""
    loader: str = ""
    dtype: str = ""
    trust_remote_code: bool = False
    torch_allocated_gib: float | None = None
    torch_reserved_gib: float | None = None
    smi_after_load_gib: float | None = None
    smi_peak_verify_gib: float | None = None
    torch_peak_allocated_gib: float | None = None
    verify_seconds: float | None = None
    verify_score: float | None = None
    input_tokens: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def _gib(mib: float) -> float:
    return round(mib / GIB, 2)


def _torch_gib(n: float) -> float:
    return round(n / (1024**3), 2)


def instance_type() -> str:
    """EC2 instance type from IMDSv2, or 'unknown' off-AWS."""
    try:
        req = urllib.request.Request(
            "http://169.254.169.254/latest/api/token",
            method="PUT",
            headers={"X-aws-ec2-metadata-token-ttl-seconds": "60"},
        )
        token = urllib.request.urlopen(req, timeout=2).read().decode()
        req = urllib.request.Request(
            "http://169.254.169.254/latest/meta-data/instance-type",
            headers={"X-aws-ec2-metadata-token": token},
        )
        return urllib.request.urlopen(req, timeout=2).read().decode()
    except Exception:  # noqa: BLE001 - off-AWS or IMDS blocked; the report says 'unknown'
        return "unknown"


def classify_error(exc: BaseException) -> tuple[str, str]:
    """GATED for a 401/403 on a repo that resolves, else NOT LOADED with the error."""
    from huggingface_hub.errors import GatedRepoError, HfHubHTTPError

    code = getattr(getattr(exc, "response", None), "status_code", None)
    if isinstance(exc, GatedRepoError) or (isinstance(exc, HfHubHTTPError) and code in (401, 403)):
        return "GATED", f"{type(exc).__name__}: {str(exc)[:200]}"
    return "NOT LOADED", f"{type(exc).__name__}: {str(exc)[:400]}"


def corpus_max_chunks(path: Path, k: int) -> list[dict[str, Any]]:
    """The ``k`` longest chunks by token count: the worst-case verify input."""
    chunks = read_chunks(path)
    return sorted(chunks, key=lambda c: c["n_tokens"], reverse=True)[:k]


def verify_prompt(chunks: list[dict[str, Any]], claim: str) -> str:
    docs = "\n\n".join(c["text"] for c in chunks)
    return (
        f"Document:\n{docs}\n\nClaim: {claim}\n"
        "Is the claim fully supported by the document? Answer yes or no.\nAnswer:"
    )


def _verify_call(model: Any, tok: Any, prompt: str) -> tuple[float, int]:
    import torch

    enc = tok(prompt, return_tensors="pt").to("cuda")
    with torch.no_grad():
        logits = model(**enc).logits[0, -1].float()
    yes = tok.encode(" yes", add_special_tokens=False)[-1]
    no = tok.encode(" no", add_special_tokens=False)[-1]
    p = torch.softmax(torch.stack([logits[no], logits[yes]]), dim=0)[1].item()
    return p, int(enc["input_ids"].shape[1])


def run_candidate(cfg: Config, repo_id: str, prompt: str) -> CandidateResult:
    import torch
    from huggingface_hub import HfApi
    from transformers import AutoModelForCausalLM, AutoTokenizer

    pin = cfg.verifier.pilot_pins[repo_id]
    res = CandidateResult(repo_id, pin.revision, trust_remote_code=pin.trust_remote_code)
    model = tok = None
    try:
        info = HfApi().model_info(repo_id, revision=pin.revision)  # resolve at the pinned sha first
        if info.sha != pin.revision:
            raise RuntimeError(f"resolved sha {info.sha} != pinned {pin.revision}")
        res.loader = "transformers AutoModelForCausalLM (in-process)"
        kw = {"revision": pin.revision, "trust_remote_code": pin.trust_remote_code}
        tok = AutoTokenizer.from_pretrained(repo_id, **kw)
        model = AutoModelForCausalLM.from_pretrained(repo_id, dtype=torch.bfloat16, **kw)
        model = model.to("cuda").eval()
        res.dtype = str(next(model.parameters()).dtype)
        if res.dtype != "torch.bfloat16":
            raise RuntimeError(f"loaded as {res.dtype}, not bf16 (D-012)")
        torch.cuda.synchronize()
        res.torch_allocated_gib = _torch_gib(torch.cuda.memory_allocated())
        res.torch_reserved_gib = _torch_gib(torch.cuda.memory_reserved())
        res.smi_after_load_gib = _gib(nvidia_smi_used_mib())
        torch.cuda.reset_peak_memory_stats()
        t0 = time.monotonic()
        with PeakSampler(cfg.loadtest.poll_seconds) as sampler:
            res.verify_score, res.input_tokens = _verify_call(model, tok, prompt)
            torch.cuda.synchronize()
        res.verify_seconds = round(time.monotonic() - t0, 2)
        res.smi_peak_verify_gib = _gib(sampler.peak)
        res.torch_peak_allocated_gib = _torch_gib(torch.cuda.max_memory_allocated())
        res.status = "PASS" if res.smi_peak_verify_gib <= cfg.loadtest.limit_gib else "FAIL"
    except Exception as e:  # noqa: BLE001 - every failure is reported, none is a pass
        res.status, res.detail = classify_error(e)
    finally:
        del model, tok
        gc.collect()
        torch.cuda.empty_cache()
    return res


def render_report(
    cfg: Config, results: list[CandidateResult], env: dict[str, Any], base: dict[str, Any]
) -> str:
    lim = cfg.loadtest.limit_gib
    lines = [
        "# A8 — co-residency load test",
        "",
        f"Rule (D-012, status 2026-10-07): device memory in use at the peak of the verify call, "
        f"read from nvidia-smi, must be <= {lim} GiB. transformers bf16, in-process; no vLLM.",
        "",
        "**The verify call is a load test. Its score is not a validated MiniCheck or Granite "
        "Guardian score** (generic yes/no prompt, not either model's template).",
        "",
        "## Environment",
        "",
        *(f"- {k}: {v}" for k, v in env.items()),
        "",
        "## Resident before the verifier",
        "",
        *(f"- {k}: {v}" for k, v in base.items()),
        "",
        "## Candidates",
        "",
        "| candidate | revision | status | loader | dtype | remote code | torch alloc / reserved "
        "(GiB) | nvidia-smi after load (GiB) | nvidia-smi peak at verify (GiB) | verify tokens "
        "| verify s |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r.repo_id} | `{r.revision[:12]}` | **{r.status}** | {r.loader or '-'} "
            f"| {r.dtype or '-'} | {r.trust_remote_code} "
            f"| {r.torch_allocated_gib} / {r.torch_reserved_gib} | {r.smi_after_load_gib} "
            f"| {r.smi_peak_verify_gib} | {r.input_tokens} | {r.verify_seconds} |"
        )
    notes = [f"- {r.repo_id}: {r.status}: {r.detail}" for r in results if r.detail]
    if notes:
        lines += ["", "## Notes", "", *notes]
    passed = [r.repo_id for r in results if r.status == "PASS"]
    lines += [
        "",
        "## Result",
        "",
        f"PASS: {passed or 'none'}. Candidates not PASS are reported, not worked around; "
        "D-012's fallback (0.6B embedder, then separate stages) is not applied by this command.",
        "",
    ]
    return "\n".join(lines)


def run_loadtest(cfg: Config, repo: Path) -> int:
    import torch
    import transformers

    from ledger.retrieval.index import Qwen3Embedder
    from ledger.retrieval.rerank import Qwen3Reranker
    from ledger.tracing import otel

    if not torch.cuda.is_available():
        print("ledger loadtest: CUDA is not available; refusing.")
        return 2
    otel.init_tracing(cfg)
    try:
        with otel.run_span("ledger.loadtest", {"rag.record_type": "loadtest_run"}) as span:
            print(f"trace id: {otel.ids_of(span)[0]}")
            print(f"{otel.ENDPOINT_ENV} set: {bool(os.environ.get(otel.ENDPOINT_ENV))}")
            top = corpus_max_chunks(repo / cfg.paths.chunks, cfg.retrieval.k_final)
            claim = "The total outlays for the fiscal year are higher than in the prior year."
            prompt = verify_prompt(top, claim)
            texts = [c["text"] for c in top]
            emb = Qwen3Embedder(cfg)
            vecs = emb.embed_documents(texts)
            assert len(vecs[0]) == cfg.embedding.dim
            rr = Qwen3Reranker(cfg)
            scores = rr.score(claim, texts)
            torch.cuda.synchronize()
            base = {
                "embedder": f"{cfg.embedding.model}@{cfg.embedding.revision[:12]} (bf16), "
                f"one embed of {len(texts)} chunks ok",
                "reranker": f"{cfg.reranker.model}@{cfg.reranker.revision[:12]} (bf16), "
                f"one rerank of {len(texts)} chunks ok (scores {[round(s, 3) for s in scores]})",
                "nvidia-smi used (GiB)": _gib(nvidia_smi_used_mib()),
                "verify input": f"{len(texts)} longest corpus chunks "
                f"({[c['n_tokens'] for c in top]} chunker tokens)",
            }
            results = [run_candidate(cfg, rid, prompt) for rid in cfg.verifier.pilot_candidates]
            env = {
                "instance type": instance_type(),
                "gpu": torch.cuda.get_device_name(0),
                "driver": subprocess.run(
                    ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
                    capture_output=True,
                    text=True,
                ).stdout.strip(),
                "torch": torch.__version__,
                "transformers": transformers.__version__,
                "platform": platform.platform(),
            }
            out = repo / cfg.paths.reports_dir / "a8.md"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(render_report(cfg, results, env, base), encoding="utf-8", newline="\n")
            print(json.dumps([r.__dict__ for r in results], indent=2, default=str))
            print(f"wrote {out}")
    finally:
        otel.shutdown_tracing()
    return 0
