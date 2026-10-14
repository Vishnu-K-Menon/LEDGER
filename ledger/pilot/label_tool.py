"""T6 console label tool (D-044 item 4; status 2026-10-14 (2)).

What the owner sees for each claim, in the committed (seeded, shuffled) order:

1. the claim; the five supplied chunks by position (1-5); the position(s) the answer cited. Never
   the question, the gold answer, a chunk ID or any verifier output. The owner records the label
   (SUPPORTED / PARTIAL / UNSUPPORTED), the position(s) where it was found, the missing
   element(s) and a note where required, and "unsure".
2. still without the answer: "stands alone".
3. the support label and "stands alone" are locked; only then is the answer text shown, for
   "entailed by the answer".

No skipping: rows are labelled in order. Every finished row is written atomically, so an
interrupted session resumes at the first unlabelled row. ``assisted`` is always false.

Display (the console is cp1252 on Windows): the tool never uses ``cli.tolerant_stdio`` (it would
print '?' for any character the stream cannot encode). It refuses unless stdout is a console
whose stream encoding is UTF-8 - on Windows, Python 3.12 writes to a console through
WriteConsoleW (PEP 528) whatever the code page; a redirected stream falls back to the ANSI code
page and is refused. Under the claim and every chunk it prints a legend of each non-ASCII
character with its Unicode name, so U+2212 / U+2013 / '-', U+00A0 / space and U+FFFD are
unambiguous whatever the font shows."""

from __future__ import annotations

import json
import unicodedata
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ledger.eval.labels import PilotLabel, PilotRelabel, PilotSlot, load_pilot_file
from ledger.pilot import repo
from ledger.pilot.sample import render_lines, write_atomic
from ledger.verify.context import context_hash, render_chunk, render_context

SELF_TEST_CHARS = ("−", "–", "-", "�", " ", "·")
MISSING_CODES = {"e": "entity", "u": "unit", "p": "period", "l": "label", "o": "other"}
LABEL_CODES = {"s": "SUPPORTED", "p": "PARTIAL", "u": "UNSUPPORTED"}

Ask = Callable[[str], str]
Say = Callable[[str], None]


class LabelToolRefused(RuntimeError):
    pass


# ---- display --------------------------------------------------------------------------------


def check_console(stream: Any) -> None:
    isatty = getattr(stream, "isatty", lambda: False)()
    enc = (getattr(stream, "encoding", None) or "").lower().replace("-", "").replace("_", "")
    if not isatty or enc != "utf8":
        raise LabelToolRefused(
            f"stdout is not a UTF-8 console (isatty={isatty}, encoding={stream.encoding!r}): run "
            "the tool directly in a PowerShell window, without redirecting or piping its output"
        )


def char_name(ch: str) -> str:
    return unicodedata.name(ch, "UNNAMED")


def legend(text: str) -> str:
    counts = Counter(ch for ch in text if ord(ch) > 127)
    if not counts:
        return ""
    parts = [f"U+{ord(ch):04X} {char_name(ch)} x{n}" for ch, n in sorted(counts.items())]
    return "   [non-ASCII: " + "; ".join(parts) + "]"


def self_test_text() -> str:
    lines = ["Character check. Each line shows one character between bars, then its name:"]
    lines += [f"  |{ch}|  U+{ord(ch):04X} {char_name(ch)}" for ch in SELF_TEST_CHARS]
    return "\n".join(lines)


# ---- items ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class LabelItem:
    claim_id: str
    question_id: str
    stratum: str
    claim: str
    chunks: tuple[str, ...]  # the five supplied chunk texts, rank order
    cited_positions: tuple[int, ...]
    answer_text: str

    @property
    def context_hash(self) -> str:
        return context_hash(render_context(self.chunks))


def build_items(
    slots: Sequence[PilotSlot | PilotLabel],
    claims: Mapping[str, Any],
    contexts: Mapping[str, Mapping[str, Any]],
    answers: Mapping[str, str],
) -> list[LabelItem]:
    """``claims``: claim_id -> ClaimRecord; ``contexts``: question_id -> contexts.jsonl record;
    ``answers``: question_id -> run-1 answer text."""
    out = []
    for s in slots:
        c = claims[s.claim_id]
        chunk_ids = [ch["chunk_id"] for ch in contexts[s.question_id]["chunks"]]
        missing = [cid for cid in c.citations if cid not in chunk_ids]
        if missing or len(chunk_ids) != 5:
            raise LabelToolRefused(f"{s.claim_id}: citations / context do not match the five")
        out.append(
            LabelItem(
                claim_id=s.claim_id,
                question_id=s.question_id,
                stratum=s.stratum,
                claim=c.text,
                chunks=tuple(render_chunk(ch["text"]) for ch in contexts[s.question_id]["chunks"]),
                cited_positions=tuple(
                    i + 1 for i, cid in enumerate(chunk_ids) if cid in c.citations
                ),
                answer_text=answers[s.question_id],
            )
        )
    return out


def screen_one(item: LabelItem, index: int, total: int) -> str:
    """Claim, chunks by position, cited position(s). No question, gold, chunk ID or verifier."""
    out = ["", "=" * 78, f"Claim {index} of {total}", "", "CLAIM:", item.claim]
    if legend(item.claim):
        out.append(legend(item.claim))
    cited = ", ".join(map(str, item.cited_positions)) or "none"
    out += ["", f"The answer cited position(s): {cited}"]
    for pos, text in enumerate(item.chunks, 1):
        out += ["", f"---- Position {pos} " + "-" * 60, text]
        if legend(text):
            out.append(legend(text))
    out.append("-" * 78)
    return "\n".join(out)


# ---- one row ------------------------------------------------------------------------------------


def _yn(ask: Ask, prompt: str) -> bool:
    while True:
        a = ask(prompt).strip().lower()
        if a in ("y", "n"):
            return a == "y"


def _codes(raw: str, table: Mapping[str, str]) -> list[str] | None:
    parts = [p for p in raw.replace(",", " ").split() if p]
    if any(p.lower() not in table for p in parts):
        return None
    return [table[p.lower()] for p in parts]


def _positions(raw: str) -> list[int] | None:
    parts = [p for p in raw.replace(",", " ").split() if p]
    if not parts or any(p not in "12345" or len(p) != 1 for p in parts):
        return None
    return [int(p) for p in parts]


def label_one(item: LabelItem, ask: Ask, say: Say, *, set_name: str = "pilot") -> dict[str, Any]:
    """Screens 1-3 for one claim. Returns the validated row; screens 1-2 are locked before the
    answer is shown (status 2026-10-14 (2))."""
    model = PilotLabel if set_name == "pilot" else PilotRelabel
    while True:
        label = None
        while label is None:
            label = LABEL_CODES.get(ask("Label [S]upported / [P]artial / [U]nsupported: ").lower())
        positions: list[int] = []
        if label != "UNSUPPORTED":
            got = None
            while got is None:
                got = _positions(ask("Position(s) where found (1-5, e.g. 2 or 1,3): "))
            positions = got
        missing: list[str] | None = [] if label == "SUPPORTED" else None
        if label == "PARTIAL":
            prompt = "Element(s) not stated (e=entity u=unit p=period l=label o=other): "
        else:
            prompt = "Cause, if an element is missing (e/u/p/l/o; blank = none): "
        while missing is None:
            missing = _codes(ask(prompt), MISSING_CODES)
        note = ask("Note (required for PARTIAL or a recorded cause; else optional): ").strip()
        unsure = _yn(ask, "Unsure? (y/n): ")
        say("(The answer is still hidden.)")
        stands_alone = _yn(ask, "Does the claim stand alone, readable on its own? (y/n): ")
        row = {
            "set": set_name,
            "claim_id": item.claim_id,
            "question_id": item.question_id,
            "stratum": item.stratum,
            "label": label,
            "found_positions": positions,
            "unsure": unsure,
            "missing_elements": missing,
            "note": note,
            "stands_alone": stands_alone,
            "entailed_by_answer": False,  # placeholder until screen 3
            "assisted": False,
            "context_hash": item.context_hash,
        }
        try:
            model(**row)
        except ValidationError as exc:
            say(f"Not accepted, redo this claim: {exc.errors()[0]['msg']}")
            continue
        if ask("Lock this and show the answer? (y = lock, r = redo this claim): ").lower() == "y":
            break
    say("\nANSWER (shown only now):\n" + item.answer_text)
    if legend(item.answer_text):
        say(legend(item.answer_text))
    row["entailed_by_answer"] = _yn(ask, "Is the claim entailed by the answer? (y/n): ")
    return model(**row).model_dump(mode="json")


# ---- the session ----------------------------------------------------------------------------


def committed_ids_match(path: Path, run: repo.Runner = repo._run) -> bool:
    """The claim ids (and order) in the working file equal the committed ones (item 3)."""
    head = repo.head_text(path, run)
    if head is None:
        return False

    def ids(text: str) -> list[str]:
        rows = [json.loads(ln) for ln in text.splitlines() if ln.strip()]
        return [r.get("claim_id") for r in rows if not r.get("manifest")]

    return ids(head) == ids(Path(path).read_text(encoding="utf-8"))


def preflight(labels_path: Path, guide_path: Path, run: repo.Runner = repo._run) -> str:
    """Refuse unless the ids are committed and the label guide is committed (item 4 + owner's
    change 2). Records the guide's SHA-256 in the manifest; refuses if it changed since."""
    if not repo.is_committed(guide_path, run):
        raise LabelToolRefused(f"{guide_path} must be committed (tracked, unmodified) first")
    if not committed_ids_match(labels_path, run):
        raise LabelToolRefused(f"{labels_path}: the claim ids must be committed before labelling")
    guide_sha = repo.sha256_file(guide_path)
    manifest, rows = load_pilot_file(labels_path)
    if manifest.label_guide_sha256 is None:
        data = manifest.model_dump(mode="json") | {"label_guide_sha256": guide_sha}
        write_atomic(labels_path, render_lines(data, [_row(r) for r in rows]))
    elif manifest.label_guide_sha256 != guide_sha:
        raise LabelToolRefused("the label guide changed since labelling started")
    return guide_sha


def _row(r: PilotSlot | PilotLabel) -> dict[str, Any]:
    return r.model_dump(mode="json")


def run_session(labels_path: Path, items: Sequence[LabelItem], ask: Ask, say: Say) -> int:
    """Label every unlabelled row in file order; returns how many were labelled now."""
    manifest, rows = load_pilot_file(labels_path)
    by_id = {it.claim_id: it for it in items}
    if [r.claim_id for r in rows] != [it.claim_id for it in items]:
        raise LabelToolRefused("items do not match the labels file rows")
    done_now = 0
    for i, r in enumerate(rows):
        if isinstance(r, PilotLabel):
            continue
        say(screen_one(by_id[r.claim_id], i + 1, len(rows)))
        rows[i] = PilotLabel(**label_one(by_id[r.claim_id], ask, say))
        write_atomic(labels_path, render_lines(manifest.model_dump(mode="json"), map(_row, rows)))
        done_now += 1
    say(f"All {len(rows)} rows are labelled. Commit {labels_path} before any verifier runs.")
    return done_now


# ---- item 6(a): the blinded relabel -------------------------------------------------------------


def run_relabel_session(out_path: Path, items: Sequence[LabelItem], ask: Ask, say: Say) -> int:
    """Relabel the selected claims (order as given: shuffled by ``relabel_selection``) into their
    own file. The first label and every verifier output stay hidden: this session never reads the
    labels file. Resumable: rows already in ``out_path`` are skipped."""
    done: dict[str, dict[str, Any]] = {}
    if out_path.exists():
        for ln in out_path.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                row = PilotRelabel(**json.loads(ln)).model_dump(mode="json")
                done[row["claim_id"]] = row
    now = 0
    for i, it in enumerate(items):
        if it.claim_id in done:
            continue
        say(screen_one(it, i + 1, len(items)))
        done[it.claim_id] = label_one(it, ask, say, set_name="pilot_relabel")
        lines = [
            json.dumps(done[x.claim_id], sort_keys=True, ensure_ascii=False)
            for x in items
            if x.claim_id in done
        ]
        write_atomic(out_path, ("\n".join(lines) + "\n").encode("utf-8"))
        now += 1
    say(f"All {len(items)} relabels written to {out_path}. Commit it, then re-run ledger pilot.")
    return now
