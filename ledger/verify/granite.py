"""Granite Guardian 3.3 8B for the T6 pilot (D-044 item 7).

think=False; the score is P(supported) = P(no) / (P(no) + P(yes)) at the verdict token after
``<score>`` (IBM's evaluation helper; the model card defines no score), computed from the logits
at that position over the two verdict-token ids recorded in part A. Polarity per the card: "yes"
= ungrounded, "no" = grounded. Each call asserts that P agrees with the parsed text
(parsed "no" <=> P > 0.5); anything else is FAIL, never a label.

The pure logic (``verdict_index``, ``p_supported``, ``judge``) is importable without a GPU; the
model is loaded only by ``GraniteScorer`` (transformers, bf16, D-012)."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from ledger.baseline.probe import parse_gg_score

GG_REPO = "ibm-granite/granite-guardian-3.3-8b"
SCORE_OPEN = "<score>"


def chat_kwargs(doc: str) -> dict:
    """The call shape the T5 probe confirmed against the pinned card (Example 3, think=False)."""
    return {
        "guardian_config": {"criteria_id": "groundedness"},
        "documents": [{"doc_id": "0", "text": doc}],
        "think": False,
        "tokenize": False,
        "add_generation_prompt": True,
    }


def verdict_index(token_texts: Sequence[str]) -> int | None:
    """Index of the first generated token after the ``<score>`` text, or None."""
    acc = ""
    for i, t in enumerate(token_texts):
        if acc.rstrip().endswith(SCORE_OPEN):
            return i
        acc += t
    return None


def p_supported(logit_no: float, logit_yes: float) -> float:
    """P(no) / (P(no) + P(yes)) from the two logits (the softmax normaliser cancels)."""
    return 1.0 / (1.0 + math.exp(logit_yes - logit_no))


@dataclass(frozen=True)
class GraniteCall:
    status: str  # ok | FAIL
    p: float | None
    parsed: str
    reason: str = ""


def judge(
    *,
    token_texts: Sequence[str],
    token_ids: Sequence[int],
    logits_at: Callable[[int], Mapping[int, float]],
    decoded: str,
    yes_id: int,
    no_id: int,
) -> GraniteCall:
    parsed = parse_gg_score(decoded) or ""
    i = verdict_index(token_texts)
    if i is None:
        return GraniteCall("FAIL", None, parsed, "no <score> in the output")
    tid = token_ids[i]
    if tid not in (yes_id, no_id):
        return GraniteCall("FAIL", None, parsed, f"verdict token id {tid} is not a recorded id")
    lg = logits_at(i)
    p = p_supported(float(lg[no_id]), float(lg[yes_id]))
    if parsed not in ("yes", "no"):
        return GraniteCall("FAIL", p, parsed, f"parsed score {parsed!r} is neither yes nor no")
    if (parsed == "no") != (tid == no_id) or (parsed == "no") != (p > 0.5):
        return GraniteCall("FAIL", p, parsed, f"P(supported) {p:.4f} disagrees with {parsed!r}")
    return GraniteCall("ok", p, parsed)


class GraniteScorer:  # pragma: no cover - GPU
    def __init__(self, revision: str, yes_id: int, no_id: int, max_new_tokens: int):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        kw = {"revision": revision}
        self.tok = AutoTokenizer.from_pretrained(GG_REPO, **kw)
        self.model = AutoModelForCausalLM.from_pretrained(GG_REPO, dtype=torch.bfloat16, **kw)
        self.model = self.model.to("cuda").eval()
        if str(next(self.model.parameters()).dtype) != "torch.bfloat16":
            raise RuntimeError("Granite Guardian is not bf16 (D-012)")
        self.yes_id, self.no_id, self.max_new = yes_id, no_id, max_new_tokens

    def generate(self, doc: str, claim: str):
        import torch

        chat = self.tok.apply_chat_template(
            [{"role": "assistant", "content": claim}], **chat_kwargs(doc)
        )
        enc = self.tok(chat, return_tensors="pt").to("cuda")
        with torch.no_grad():
            out = self.model.generate(
                **enc,
                max_new_tokens=self.max_new,
                do_sample=False,
                output_logits=True,
                return_dict_in_generate=True,
            )
        ids = [int(t) for t in out.sequences[0, enc["input_ids"].shape[1] :]]
        texts = [self.tok.decode([t]) for t in ids]
        decoded = self.tok.decode(ids, skip_special_tokens=True)
        return ids, texts, decoded, out.logits

    def score(self, doc: str, claim: str) -> GraniteCall:
        ids, texts, decoded, logits = self.generate(doc, claim)

        def logits_at(i: int) -> Mapping[int, float]:
            row = logits[i][0].float()
            return {self.yes_id: float(row[self.yes_id]), self.no_id: float(row[self.no_id])}

        return judge(
            token_texts=texts,
            token_ids=ids,
            logits_at=logits_at,
            decoded=decoded,
            yes_id=self.yes_id,
            no_id=self.no_id,
        )
