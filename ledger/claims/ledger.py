"""The claim ledger — the loop state (D20/D21). Built in T10; only the name is fixed here.

Naming rule (CLAUDE.md): the project, the CLI and this data structure are all "ledger"; the
Python package is ``ledger/`` and this class lives here to avoid a ``ledger/ledger.py`` collision.
"""


class ClaimLedger:
    """Ordered rows of ``claim_id, text, source_sentence_idx, citations, qualifiers, verdict,
    score, evidence_ids, iter_first_seen, iter_resolved, action_taken, replaces, trace_id,
    span_id`` (D21, D-017). Invariants and tests arrive with T10."""

    def __init__(self) -> None:
        raise NotImplementedError("ClaimLedger is built in T10")
