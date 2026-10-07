"""Qwen3-Reranker as a yes/no LM scorer (CLAUDE.md: not a drop-in cross-encoder).

This is the official scoring snippet from the model card (README.md at the pinned revision,
"Transformers Usage"): a prompt with the card's fixed system prefix and think-less assistant
suffix, then ``P("yes")`` from the last-position logits restricted to {"no", "yes"}.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ledger.config import Config

# Verbatim from the card.
PREFIX = (
    "<|im_start|>system\nJudge whether the Document meets the requirements based on the Query and "
    'the Instruct provided. Note that the answer can only be "yes" or "no".<|im_end|>\n'
    "<|im_start|>user\n"
)
SUFFIX = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
DEFAULT_INSTRUCTION = "Given a web search query, retrieve relevant passages that answer the query"


def format_instruction(instruction: str | None, query: str, doc: str) -> str:
    instruction = instruction or DEFAULT_INSTRUCTION
    return f"<Instruct>: {instruction}\n<Query>: {query}\n<Document>: {doc}"


class Qwen3Reranker:
    def __init__(self, cfg: Config):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self._torch = torch
        self.max_length = cfg.reranker.max_length
        self.tok = AutoTokenizer.from_pretrained(
            cfg.reranker.model, revision=cfg.reranker.revision, padding_side="left"
        )
        self.model = (
            AutoModelForCausalLM.from_pretrained(
                cfg.reranker.model, revision=cfg.reranker.revision, dtype=torch.bfloat16
            )
            .to("cuda")
            .eval()
        )
        self.true_id = self.tok.convert_tokens_to_ids("yes")
        self.false_id = self.tok.convert_tokens_to_ids("no")
        self.prefix = self.tok.encode(PREFIX, add_special_tokens=False)
        self.suffix = self.tok.encode(SUFFIX, add_special_tokens=False)

    def score(self, query: str, docs: Sequence[str], instruction: str | None = None) -> list[Any]:
        torch = self._torch
        pairs = [format_instruction(instruction, query, d) for d in docs]
        budget = self.max_length - len(self.prefix) - len(self.suffix)
        enc = self.tok(
            pairs,
            padding=False,
            truncation="longest_first",
            return_attention_mask=False,
            max_length=budget,
        )
        enc["input_ids"] = [self.prefix + ids + self.suffix for ids in enc["input_ids"]]
        batch = self.tok.pad(enc, padding=True, return_tensors="pt", max_length=self.max_length)
        batch = {k: v.to(self.model.device) for k, v in batch.items()}
        with torch.no_grad():
            logits = self.model(**batch).logits[:, -1, :]
        two = torch.stack([logits[:, self.false_id], logits[:, self.true_id]], dim=1)
        return torch.nn.functional.log_softmax(two, dim=1)[:, 1].exp().tolist()
