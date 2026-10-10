# ruff: noqa: E501
"""T5 verifier probe (GPU; not run in the build pass). One verifier resident at a time, bf16
transformers, no vLLM (D-012). Writes reports/t5_verifier_probe.md.

MiniCheck (bespokelabs/Bespoke-MiniCheck-7B at the pinned revision):
  (a) scoring forward pass with ``use_cache=False`` (A8 failed in remote code on
      ``DynamicCache.from_legacy_cache``); the official system/user prompt and the P("yes")
      rule come from github.com/Liyan06/MiniCheck at a pinned commit (ledger/baseline/probe.py);
  pass = the README example reproduced (0.984 / 0.011, +/- 0.02), then 4 supported + 4
  digit-altered claims at one-chunk and five-chunk context.
  (b) If (a) still fails, the exception is reported verbatim and this script stops for MiniCheck.
  It does NOT apply an unreviewed shim; candidate fixes are the planning chat's to choose.
Granite Guardian 3.3 8B (pinned revision): its official groundedness template through the
tokenizer's chat template (``guardian_config={"criteria_id": "groundedness"}``, ``think=False``),
README at the pinned revision checked for the call shape; "yes" = ungrounded (its card).

If a template or example cannot be found at its pinned source the probe stops for that verifier
and says so in the report.

    uv run python scripts/t5_verifier_probe.py
"""

from __future__ import annotations

import gc
import sys
import traceback
from collections import defaultdict
from pathlib import Path

from ledger.baseline import probe
from ledger.baseline.runtime import read_questions
from ledger.config import load_config
from ledger.retrieval.index import read_chunks

QUESTIONS = Path("data/questions_draft.jsonl")
OUT = Path("reports/t5_verifier_probe.md")
MC = "bespokelabs/Bespoke-MiniCheck-7B"
GG = "ibm-granite/granite-guardian-3.3-8b"


def _load(cfg, repo_id):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    pin = cfg.verifier.pilot_pins[repo_id]
    kw = {"revision": pin.revision, "trust_remote_code": pin.trust_remote_code}
    tok = AutoTokenizer.from_pretrained(repo_id, **kw)
    model = AutoModelForCausalLM.from_pretrained(repo_id, dtype=torch.bfloat16, **kw)
    model = model.to("cuda").eval()
    if str(next(model.parameters()).dtype) != "torch.bfloat16":
        raise RuntimeError("not bf16 (D-012)")
    return model, tok


def _unload():
    import torch

    gc.collect()
    torch.cuda.empty_cache()


# ---- MiniCheck ----------------------------------------------------------------------------------


def minicheck_scorer(model, tok, system_prompt, user_prompt):
    import torch

    def score(doc: str, claim: str) -> float:
        text = tok.apply_chat_template(
            [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": user_prompt.replace("[DOCUMENT]", doc).replace("[CLAIM]", claim),
                },
            ],
            add_generation_prompt=True,
            tokenize=False,
        )
        enc = tok(text, return_tensors="pt").to("cuda")  # vLLM tokenizes a text prompt this way
        with torch.no_grad():
            logits = model(**enc, use_cache=False).logits[0, -1].float()  # (a) use_cache=False
        logprobs = torch.log_softmax(logits, dim=-1)
        top = torch.topk(logprobs, 5)
        pairs = [
            (tok.decode([int(i)]), float(lp)) for lp, i in zip(top.values, top.indices, strict=True)
        ]
        return probe.support_prob(pairs)

    return score


def run_minicheck(cfg, fetch, claims, sources):
    pin = cfg.verifier.pilot_pins[MC]
    gh = lambda path, role: probe.fetch_source(  # noqa: E731
        role,
        probe.MINICHECK_REPO,
        path,
        probe.MINICHECK_COMMIT,
        probe.github_url(probe.MINICHECK_REPO, probe.MINICHECK_COMMIT, path),
        fetch,
    )
    utils = gh(probe.MINICHECK_UTILS, "MiniCheck system/user prompt")
    inference = gh(probe.MINICHECK_INFERENCE, "MiniCheck apply_chat_template + P(yes) rule")
    gh_readme = gh(probe.MINICHECK_README, "MiniCheck README example + expected numbers")
    hf_readme = probe.fetch_source(
        "Bespoke-MiniCheck-7B model card (cross-check of the numbers)",
        MC,
        "README.md",
        pin.revision,
        probe.hf_url(MC, pin.revision, "README.md"),
        fetch,
    )
    sources += [utils, inference, gh_readme, hf_readme]
    system_prompt, user_prompt = probe.extract_prompts(utils.text)
    example = probe.extract_readme_example(gh_readme.text)
    cross = probe.extract_readme_example(hf_readme.text)
    if cross["expected"] != example["expected"]:
        raise probe.ProbeStop("README numbers differ between the GitHub README and the model card")

    model, tok = _load(cfg, MC)
    try:
        score = minicheck_scorer(model, tok, system_prompt, user_prompt)
        got = [score(example["doc"], example["claim_1"]), score(example["doc"], example["claim_2"])]
        ok = probe.within(got, example["expected"])
        lines = [
            f"README example (expected {example['expected']}): got {got} -> "
            f"**{'REPRODUCED' if ok else 'NOT REPRODUCED'}** (tolerance +/- {probe.README_TOLERANCE})",
            "",
            "| question | label | context chunks | P(yes) | predicted supported | correct |",
            "|---|---|---|---|---|---|",
        ]
        tally = defaultdict(lambda: [0, 0])
        for c in claims:
            p = score(c["doc"], c["claim"])
            ok_c = probe.correct(c["label"], p > 0.5)
            tally[(c["label"], c["context_chunks"])][0] += ok_c
            tally[(c["label"], c["context_chunks"])][1] += 1
            lines.append(
                f"| {c['question_id']} | {c['label']} | {c['context_chunks']} | {p:.3f} | {p > 0.5} | {ok_c} |"
            )
        lines += ["", "| label | context chunks | correct |", "|---|---|---|"]
        lines += [f"| {k[0]} | {k[1]} | {v[0]}/{v[1]} |" for k, v in sorted(tally.items())]
        return "\n".join(lines)
    finally:
        del model, tok
        _unload()


# ---- Granite Guardian ----------------------------------------------------------------------------


def run_granite(cfg, fetch, claims, sources):
    import torch

    pin = cfg.verifier.pilot_pins[GG]
    readme = probe.fetch_source(
        "Granite Guardian 3.3 model card (call shape, polarity, score parsing)",
        GG,
        "README.md",
        pin.revision,
        probe.hf_url(GG, pin.revision, "README.md"),
        fetch,
    )
    sources.append(readme)
    probe.check_gg_readme(readme.text)
    model, tok = _load(cfg, GG)
    try:
        lines = [
            "Template: `tokenizer.apply_chat_template([{'role': 'assistant', 'content': claim}], "
            "guardian_config={'criteria_id': 'groundedness'}, documents=[{'doc_id': '0', 'text': doc}], "
            "think=False, tokenize=False, add_generation_prompt=True)` (README at the pinned revision, "
            "Example 3 with think=False as in its Examples 1-2). Polarity per the card: `yes` = "
            "ungrounded, `no` = grounded.",
            "",
            "| question | label | context chunks | raw output | parsed | predicted supported | correct |",
            "|---|---|---|---|---|---|---|",
        ]
        tally = defaultdict(lambda: [0, 0])
        for c in claims:
            chat = tok.apply_chat_template(
                [{"role": "assistant", "content": c["claim"]}],
                guardian_config={"criteria_id": "groundedness"},
                documents=[{"doc_id": "0", "text": c["doc"]}],
                think=False,
                tokenize=False,
                add_generation_prompt=True,
            )
            enc = tok(chat, return_tensors="pt").to("cuda")
            with torch.no_grad():
                out = model.generate(**enc, max_new_tokens=24, do_sample=False)
            raw = tok.decode(out[0, enc["input_ids"].shape[1] :], skip_special_tokens=True)
            parsed = probe.parse_gg_score(raw)
            supported = parsed == "no"
            ok_c = parsed in ("yes", "no") and probe.correct(c["label"], supported)
            tally[(c["label"], c["context_chunks"])][0] += ok_c
            tally[(c["label"], c["context_chunks"])][1] += 1
            lines.append(
                f"| {c['question_id']} | {c['label']} | {c['context_chunks']} | "
                f"`{raw.strip()[:60]}` | {parsed} | {supported} | {ok_c} |"
            )
        lines += ["", "| label | context chunks | correct |", "|---|---|---|"]
        lines += [f"| {k[0]} | {k[1]} | {v[0]}/{v[1]} |" for k, v in sorted(tally.items())]
        return "\n".join(lines)
    finally:
        del model, tok
        _unload()


def main() -> int:
    import torch
    import transformers

    if not torch.cuda.is_available():
        print("t5_verifier_probe: CUDA is not available; refusing (GPU stage).")
        return 2
    cfg = load_config()
    questions = read_questions(QUESTIONS)
    chunks = read_chunks(cfg.paths.chunks)
    by_id = {c["chunk_id"]: c for c in chunks}
    units = defaultdict(list)
    for c in chunks:
        units[c["unit_id"]].append(c)
    claims = probe.build_probe_claims(questions, by_id, units)
    env = {
        "torch": torch.__version__,
        "transformers": transformers.__version__,
        "gpu": torch.cuda.get_device_name(0),
        "claims": f"{len(claims)} ({len(claims) // 4} per label x context cell, 4 questions)",
        "claim form": 'mechanical: The answer to the question "<q>" is <gold answer>. '
        "(altered = last digit +1); this tests digit sensitivity, not natural claims",
        "minicheck pinned": f"{probe.MINICHECK_REPO}@{probe.MINICHECK_COMMIT}",
        "minicheck model": f"{MC}@{cfg.verifier.pilot_pins[MC].revision}",
        "granite model": f"{GG}@{cfg.verifier.pilot_pins[GG].revision}",
    }
    sources: list[probe.Source] = []
    sections: dict[str, str] = {}
    stops: dict[str, str] = {}
    for name, fn in (
        ("Bespoke-MiniCheck-7B", run_minicheck),
        ("Granite Guardian 3.3 8B", run_granite),
    ):
        try:
            sections[name] = fn(cfg, probe.default_fetch, claims, sources)
        except probe.ProbeStop as exc:
            stops[name] = str(exc)
        except Exception as exc:  # noqa: BLE001 - reported verbatim, nothing is worked around
            stops[name] = f"{type(exc).__name__}: {exc}"
            sections[name] = "```\n" + traceback.format_exc() + "\n```"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        probe.render_report(env, sources, sections, stops), encoding="utf-8", newline="\n"
    )
    print(f"wrote {OUT}; stops: {list(stops) or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
