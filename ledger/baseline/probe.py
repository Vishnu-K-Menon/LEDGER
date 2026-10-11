"""Logic for the T5 verifier probe (no GPU, no network at import). The official prompt templates and
the README example values come from NAMED, PINNED sources fetched at run time and recorded with
their sha256; nothing is reconstructed from memory. If a template cannot be found at its pinned
source, the probe stops for that verifier (``ProbeStop``) and the report says so."""

from __future__ import annotations

import ast
import hashlib
import math
import re
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

# MiniCheck's own repo, pinned to the commit current on 2026-10-09 (committed 2025-08-27).
MINICHECK_REPO = "Liyan06/MiniCheck"
MINICHECK_COMMIT = "b58b9fa69acbd1015ec970fa65dd752413a053d2"
MINICHECK_UTILS = "minicheck/utils.py"  # SYSTEM_PROMPT, USER_PROMPT
MINICHECK_INFERENCE = "minicheck/inference.py"  # apply_chat_template, get_support_prob
MINICHECK_README = "README.md"  # the Bespoke-MiniCheck-7B example and its numbers

README_TOLERANCE = 0.02  # owner: 0.984 and 0.011, +/- 0.02


class ProbeStop(RuntimeError):
    """A template or example could not be found at its pinned source: stop for this verifier."""


@dataclass(frozen=True)
class Source:
    role: str
    repo: str
    path: str
    revision: str
    url: str
    sha256: str
    text: str


Fetcher = Callable[[str], bytes]


def default_fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as resp:  # noqa: S310 - fixed https hosts
        return resp.read()


def github_url(repo: str, commit: str, path: str) -> str:
    return f"https://raw.githubusercontent.com/{repo}/{commit}/{path}"


def hf_url(repo: str, revision: str, path: str) -> str:
    return f"https://huggingface.co/{repo}/raw/{revision}/{path}"


def fetch_source(
    role: str, repo: str, path: str, revision: str, url: str, fetch: Fetcher
) -> Source:
    try:
        raw = fetch(url)
    except Exception as exc:  # noqa: BLE001
        raise ProbeStop(f"{role}: cannot fetch {url}: {exc!r}") from exc
    return Source(
        role, repo, path, revision, url, hashlib.sha256(raw).hexdigest(), raw.decode("utf-8")
    )


def extract_prompts(utils_py: str) -> tuple[str, str]:
    """SYSTEM_PROMPT and USER_PROMPT from MiniCheck's utils.py, by parsing (never executing) it."""
    found: dict[str, str] = {}
    for node in ast.parse(utils_py).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id in ("SYSTEM_PROMPT", "USER_PROMPT"):
                found[target.id] = ast.literal_eval(node.value)
    if set(found) != {"SYSTEM_PROMPT", "USER_PROMPT"}:
        raise ProbeStop("MiniCheck utils.py at the pinned commit lacks SYSTEM_PROMPT / USER_PROMPT")
    if "[DOCUMENT]" not in found["USER_PROMPT"] or "[CLAIM]" not in found["USER_PROMPT"]:
        raise ProbeStop("USER_PROMPT has no [DOCUMENT] / [CLAIM] placeholders")
    return found["SYSTEM_PROMPT"], found["USER_PROMPT"]


_BESPOKE_SECTION = re.compile(
    r"model_name\s*=\s*'Bespoke-MiniCheck-7B'.*?print\(raw_prob\)\s*#\s*\[([^\]]+)\]", re.S
)


def extract_readme_example(readme: str) -> dict[str, Any]:
    """The doc, the two claims and the expected Bespoke-MiniCheck-7B probabilities."""
    out: dict[str, Any] = {}
    for name in ("doc", "claim_1", "claim_2"):
        m = re.search(rf'^{name}\s*=\s*"([^"]+)"', readme, re.M)
        if not m:
            raise ProbeStop(f"README example has no {name}")
        out[name] = m.group(1)
    m = _BESPOKE_SECTION.search(readme)
    if not m:
        raise ProbeStop("README has no Bespoke-MiniCheck-7B example output")
    out["expected"] = [float(x) for x in m.group(1).split(",")]
    if len(out["expected"]) != 2:
        raise ProbeStop("README example output is not two numbers")
    return out


def support_prob(top: Sequence[tuple[str, float]]) -> float:
    """MiniCheck ``get_support_prob`` (inference.py at the pinned commit): over the top-5
    first-position tokens, sum exp(logprob) of those whose decoded text lower-cased is 'yes'."""
    return sum(math.exp(lp) for tok, lp in top if tok.lower() == "yes")


def within(got: Sequence[float], want: Sequence[float], tol: float = README_TOLERANCE) -> bool:
    return len(got) == len(want) and all(abs(g - w) <= tol for g, w in zip(got, want, strict=True))


def parse_gg_score(text: str) -> str | None:
    """Granite Guardian: the last ``<score> ... </score>`` (README at the pinned revision)."""
    found = re.findall(r"<score>(.*?)</score>", text, re.S)
    return found[-1].strip().lower() if found else None


GG_README_MARKERS = (
    '"criteria_id": "groundedness"',
    "think=",
    'risky_token = "yes"',
    "<score>(.*?)</score>",
)


def check_gg_readme(readme: str) -> None:
    missing = [m for m in GG_README_MARKERS if m not in readme]
    if missing:
        raise ProbeStop(f"Granite Guardian README at the pinned revision lacks: {missing}")


# ---- claims -----------------------------------------------------------------------------------


def alter_digits(answer: str) -> str:
    """Change the last digit of ``answer`` (d -> d+1 mod 10). The digit-altered claim differs from
    the supported one in exactly one digit."""
    for i in range(len(answer) - 1, -1, -1):
        if answer[i].isdigit():
            return answer[:i] + str((int(answer[i]) + 1) % 10) + answer[i + 1 :]
    raise ValueError(f"no digit in {answer!r}")


def claim_for(question: str, answer: str) -> str:
    return f'The answer to the question "{question}" is {answer}.'


def build_probe_claims(
    questions: Sequence[Mapping[str, Any]],
    chunks_by_id: Mapping[str, Mapping[str, Any]],
    units: Mapping[str, Sequence[Mapping[str, Any]]],
    n: int = 4,
    context_chunks: int = 5,
) -> list[dict[str, Any]]:
    """4 supported + 4 digit-altered claims from the first ``n`` numeric draft questions, each at
    one-chunk and five-chunk context (the gold chunk, then same-unit neighbours in file order)."""
    picked = [
        q
        for q in questions
        if q.get("set", "draft") == "draft"
        and not q.get("unanswerable")
        and q.get("answer_type") == "number"
        and any(ch.isdigit() for ch in str(q["gold_answer"]))
    ][:n]
    out = []
    for q in picked:
        gold = chunks_by_id[q["gold_chunk_id"]]
        neighbours = [c for c in units[gold["unit_id"]] if c["chunk_id"] != gold["chunk_id"]]
        contexts = {
            1: gold["text"],
            context_chunks: "\n\n".join(
                c["text"] for c in [gold, *neighbours[: context_chunks - 1]]
            ),
        }
        for label, answer in (
            ("supported", q["gold_answer"]),
            ("altered", alter_digits(q["gold_answer"])),
        ):
            for size, doc in contexts.items():
                out.append(
                    {
                        "question_id": q["question_id"],
                        "label": label,
                        "context_chunks": size,
                        "claim": claim_for(q["question"], answer),
                        "doc": doc,
                    }
                )
    return out


def correct(label: str, supported: bool) -> bool:
    return supported if label == "supported" else not supported


NOT_INTERPRETABLE = "not interpretable: README example not reproduced"


def render_top5(pairs: Sequence[tuple[str, float]]) -> str:
    """The first-position top-5 as ``repr(token): logprob`` (repr, so leading spaces show)."""
    return "; ".join(f"{tok!r}: {lp:.3f}".replace("|", "\\|") for tok, lp in pairs)


def minicheck_section(
    example: Mapping[str, Any],
    got: Sequence[float],
    example_top5: Sequence[Sequence[tuple[str, float]]],
    ok: bool,
    rows: Sequence[Mapping[str, Any]],
) -> tuple[str, str | None]:
    """The MiniCheck report section and, when the README example is not reproduced, the stop
    message. A stop carries no 'correct' column and no tally: nothing there is a result. The
    top-5 of every call is written either way (the diagnosis)."""
    verdict = "REPRODUCED" if ok else "NOT REPRODUCED"
    lines = [
        f"README example (expected {example['expected']}): got {list(got)} -> "
        f"**{verdict}** (tolerance +/- {README_TOLERANCE})",
        "",
        "Top-5 first-position (decoded token, logprob) for the two README calls:",
        "",
    ]
    lines += [f"- claim {i}: {render_top5(t)}" for i, t in enumerate(example_top5, 1)]
    lines.append("")
    if ok:
        lines += [
            "| question | label | context chunks | P(yes) | predicted supported | correct "
            "| top-5 (token: logprob) |",
            "|---|---|---|---|---|---|---|",
        ]
        tally: dict[tuple[str, int], list[int]] = {}
        for r in rows:
            sup = r["p"] > 0.5
            hit = correct(r["label"], sup)
            t = tally.setdefault((r["label"], r["context_chunks"]), [0, 0])
            t[0] += hit
            t[1] += 1
            lines.append(
                f"| {r['question_id']} | {r['label']} | {r['context_chunks']} | {r['p']:.3f} | "
                f"{sup} | {hit} | {render_top5(r['top5'])} |"
            )
        lines += ["", "| label | context chunks | correct |", "|---|---|---|"]
        lines += [f"| {k[0]} | {k[1]} | {v[0]}/{v[1]} |" for k, v in sorted(tally.items())]
        return "\n".join(lines), None
    lines += [
        f"**{NOT_INTERPRETABLE}.** The rows below carry P(yes) and the top-5 only; no 'correct' "
        "tally is presented as a result for this verifier.",
        "",
        "| question | label | context chunks | P(yes) | top-5 (token: logprob) |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['question_id']} | {r['label']} | {r['context_chunks']} | {r['p']:.3f} | "
            f"{render_top5(r['top5'])} |"
        )
    stop = (
        f"README example not reproduced (got {list(got)}, "
        f"expected {list(example['expected'])}); {NOT_INTERPRETABLE}"
    )
    return "\n".join(lines), stop


# ---- report -----------------------------------------------------------------------------------


def render_report(
    env: Mapping[str, Any],
    sources: Sequence[Source],
    sections: Mapping[str, str],
    stops: Mapping[str, str],
) -> str:
    out = ["# T5 verifier probe", ""]
    out.append(
        "Harness probe for T6 (D-003, D-004, D-012). **No scoring decision is made here**; no vLLM "
        "environment; bf16 transformers, one verifier resident at a time.\n"
    )
    out.append("## Environment\n")
    out += [f"- {k}: `{v}`" for k, v in env.items()]
    out += [
        "",
        "## Pinned sources (templates and examples are read from these, never from memory)",
        "",
    ]
    out.append("| role | repo | file | revision / commit | sha256 of the fetched file |")
    out.append("|---|---|---|---|---|")
    for s in sources:
        out.append(f"| {s.role} | {s.repo} | `{s.path}` | `{s.revision}` | `{s.sha256}` |")
    if stops:
        out += ["", "## Stopped", ""]
        out += [f"- **{v}**: {msg}" for v, msg in stops.items()]
    for name, text in sections.items():
        out += ["", f"## {name}", "", text]
    return "\n".join(out) + "\n"
