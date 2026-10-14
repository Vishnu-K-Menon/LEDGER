"""``ledger pilot`` (D-044 items 5-7, 10, 11): the readability gate, then - once the scores exist -
every kappa with answer-clustered intervals, AUROC, eligibility, balanced accuracy and the outcome
(GO / NO-GO CANDIDATE / INCONCLUSIVE). It recommends only: it writes the gate and pilot reports
and nothing else (no decision, config value or plan tick)."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from ledger.config import Config
from ledger.eval import kappa as K
from ledger.eval import pilot_outcome as O
from ledger.eval.labels import LabelsRefused, PilotLabel, load_pilot_labels, load_relabels
from ledger.pilot import repo
from ledger.verify.scores import MODES, ScoreRow, read_scores

REFUSED = 3


class PilotRefused(RuntimeError):
    pass


def _f(x) -> str:
    return "undefined" if x is None else f"{float(x):.4f}"


def gate_report(path: Path, labels: Sequence[PilotLabel], g: O.Gate, cfg: Config) -> str:
    strata = dict(sorted(Counter(lab.stratum for lab in labels).items()))
    a3 = (
        "undefined (no claim flagged entailed)"
        if g.a3_rate is None
        else (
            f"{g.n_entailed_unsupported}/{g.n_entailed} = {float(g.a3_rate):.4f} "
            f"-> {'PASS' if g.a3_pass else 'FAIL'} (>= {cfg.pilot.a3_min_rate})"
        )
    )
    lines = [
        "# T6 readability gate (D-044 item 5)",
        "",
        f"- labels: `{Path(path).as_posix()}` sha256 `{repo.sha256_file(path)}`",
        f"- claims labelled: {len(labels)}; strata (as they fell): {strata}",
        f"- k (UNSUPPORTED or PARTIAL): {g.k}; m (SUPPORTED): {g.m}",
        f"- binary kappa readable (k >= {cfg.pilot.readable_min_each} and m >= "
        f"{cfg.pilot.readable_min_each}): **{'YES' if g.readable else 'NO'}**",
        f"- labels: {dict(sorted(Counter(lab.label for lab in labels).items()))}; "
        f"unsure {sum(lab.unsure for lab in labels)}; "
        f"stands alone {sum(lab.stands_alone for lab in labels)}; "
        f"entailed by the answer {g.n_entailed}",
        f"- A3 (UNSUPPORTED, PARTIAL folded in, on claims entailed by the answer): {a3}",
        "",
        "Counted from the committed labels file before any verifier runs. Pilot labels are never "
        "pooled into the week-3 kappa (D-044 item 6(c)).",
    ]
    return "\n".join(lines) + "\n"


def _cells(rows: Sequence[ScoreRow], kind: str) -> dict[tuple[str, str], list[ScoreRow]]:
    out: dict[tuple[str, str], list[ScoreRow]] = {}
    for r in rows:
        if r.kind == kind:
            out.setdefault((r.verifier, r.mode), []).append(r)
    return out


def run_pilot(cfg: Config, labels_path: Path, run: repo.Runner = repo._run) -> tuple[int, str]:
    labels_path = Path(labels_path)
    try:
        if not repo.is_committed(labels_path, run):
            raise PilotRefused(f"{labels_path} must be committed before the gate is read")
        manifest, labels = load_pilot_labels(labels_path)
    except (PilotRefused, LabelsRefused) as exc:
        return REFUSED, f"ledger pilot REFUSED: {exc}"
    g = O.gate(labels, cfg)
    gtext = gate_report(labels_path, labels, g, cfg)
    gpath = Path(cfg.pilot.paths.gate_report)
    gpath.parent.mkdir(parents=True, exist_ok=True)
    gpath.write_bytes(gtext.encode("utf-8"))
    scores_path = Path(cfg.pilot.paths.scores)
    if not scores_path.exists():
        return 0, gtext + f"\nNo scores yet ({scores_path}): gate only. Commit {gpath}.\n"
    try:
        text = _outcome(cfg, labels_path, manifest.n, labels, g, scores_path)
    except (PilotRefused, K.KappaRefused) as exc:
        return REFUSED, gtext + f"\nledger pilot REFUSED (no kappa, BA or branch computed): {exc}\n"
    out = Path(cfg.pilot.paths.pilot_report)
    out.write_bytes((gtext + "\n" + text).encode("utf-8"))
    return 0, gtext + "\n" + text


def _outcome(cfg, labels_path, n, labels, g, scores_path) -> str:
    sm, rows = read_scores(scores_path)
    if sm.labels_sha256 != repo.sha256_file(labels_path):
        raise PilotRefused("the scores were made on a different labels file")
    part_a = Path(cfg.pilot.paths.part_a)
    if not part_a.exists() or repo.sha256_file(part_a) != sm.part_a_sha256:
        raise PilotRefused(f"{part_a} is missing or is not the part A the scores were made after")
    scored = [v for v, s in sm.verifiers.items() if s == "PASS"]
    cells = _cells(rows, "claim")
    want = [(v, m) for v in scored for m in MODES]
    if set(cells) != set(want):
        raise PilotRefused(f"score cells {sorted(cells)} != expected {sorted(want)}")
    # every refusal (FAIL, count, ids) is checked for every cell before anything is computed
    aligned = {cell: K.align(labels, cells[cell], n) for cell in want}
    pc = cfg.pilot
    stats = {
        cell: K.cell_stats(
            pairs,
            threshold=cfg.verifier.threshold,
            n_boot=cfg.eval.bootstrap_n,
            seed=pc.bootstrap_seed,
            level=pc.ci_level,
        )
        for cell, pairs in aligned.items()
    }
    out = ["# T6 kappa pilot (D-044)", ""]
    out += [f"- scores: `{scores_path.as_posix()}` sha256 `{repo.sha256_file(scores_path)}`"]
    out += [f"- verifiers: {sm.verifiers}; revisions {sm.revisions}; git `{sm.git_commit}`", ""]
    out += [f"**{K.FOLD_NOTE}** (governing):", ""]
    out += ["| verifier | mode | n | kappa (binary) | interval | AUROC | interval |"]
    out += ["|---|---|---|---|---|---|---|"]
    for cell, s in stats.items():
        out.append(
            f"| {cell[0]} | {cell[1]} | {s.n} | {_f(s.kappa_binary)} | "
            f"{s.kappa_binary_ci.text(pc.ci_level)} | {_f(s.auroc)} | "
            f"{s.auroc_ci.text(pc.ci_level)} |"
        )
    out += ["", f"Secondary - {K.THREE_CLASS_NOTE}; partial rate {K.partial_rate(labels):.4f}:", ""]
    out += [f"- {c[0]} / {c[1]}: kappa_3class {_f(s.kappa_3class)}" for c, s in stats.items()]
    out += ["", "Not governing - kappa with PARTIAL folded into SUPPORTED:", ""]
    out += [
        f"- {c[0]} / {c[1]}: {_f(s.kappa_partial_to_supported)} "
        f"{s.kappa_partial_to_supported_ci.text(pc.ci_level)}"
        for c, s in stats.items()
    ]
    out += ["", f"PARTIAL causes (not governing): {K.partial_causes(labels)}", ""]

    if g.readable:
        r = O.choose_readable({c: s.kappa_binary for c, s in stats.items()}, cfg)
        out += [f"## Outcome: **{r.outcome}** (readable, item 6(a))", "", f"- {r.why}"]
        if r.verifier:
            out.append(f"- verifier: {r.verifier}; mode (D-004): {r.mode}")
        if r.outcome == O.NO_GO_CANDIDATE:
            # status 2026-10-14 (1): the verifier x mode cell with the best binary kappa
            best_cell = max(
                (c for c, s in stats.items() if s.kappa_binary is not None),
                key=lambda c: stats[c].kappa_binary,
            )
            ids = O.relabel_selection(aligned[best_cell], cfg)
            sel = Path(cfg.paths.results_dir) / "t6" / "relabel_ids.json"
            sel.parent.mkdir(parents=True, exist_ok=True)
            sel.write_text(json.dumps(ids), encoding="utf-8")
            out.append(f"- blinded relabel set ({len(ids)} claims) written to `{sel.as_posix()}`")
        out += _relabel_section(cfg, labels, n, aligned, stats)
    else:
        tallies = {
            v: (
                O.tally(aligned[(v, "concatenated")], cfg.verifier.threshold)
                if v in scored
                else None
            )
            for v in cfg.verifier.pilot_candidates
        }
        passed = {v: sm.verifiers.get(v) == "PASS" for v in cfg.verifier.pilot_candidates}
        ch = O.choose_not_readable(tallies, passed, cfg)
        head = (
            f"## Outcome: **{O.INCONCLUSIVE}** (not readable, item 6(b)); no kappa branch is taken"
        )
        out += [head, ""]
        for v in cfg.verifier.pilot_candidates:
            t = tallies[v]
            desc = (
                "not scored"
                if t is None
                else (f"TP {t.tp}/{t.k}, TN {t.tn}/{t.m}, BA {_f(ch.ba.get(v))}")
            )
            elig = (
                "eligible" if not ch.eligible[v] else "NOT eligible: " + "; ".join(ch.eligible[v])
            )
            out.append(f"- {v} (concatenated): {desc}; {elig}")
        if ch.verifier:
            out.append(
                f"- provisional verifier: **{ch.verifier}**, mode concatenated - PROVISIONAL, "
                "confirmed or reversed by kappa on the first 50 T7 baseline labels before T10"
            )
        out.append(f"- rule: {ch.why}")
        out.append("- INCONCLUSIVE never triggers the switch.")
    out += _panel_section(rows, cfg)
    return "\n".join(out) + "\n"


def _relabel_section(cfg, labels, n, aligned, stats) -> list[str]:
    path = Path(cfg.pilot.paths.relabel)
    if not path.exists():
        return []
    re = {r.claim_id: r for r in load_relabels(path)}
    swapped = [
        PilotLabel(**{**lab.model_dump(), **re[lab.claim_id].model_dump(), "set": "pilot"})
        if lab.claim_id in re
        else lab
        for lab in labels
    ]
    out = ["", f"### After the blinded relabel ({len(re)} claims); pre-relabel kappa above", ""]
    for cell, pairs in aligned.items():
        rows = [row for _, row in pairs]
        s = K.cell_stats(
            K.align(swapped, rows, n),
            threshold=cfg.verifier.threshold,
            n_boot=cfg.eval.bootstrap_n,
            seed=cfg.pilot.bootstrap_seed,
            level=cfg.pilot.ci_level,
        )
        out.append(
            f"- {cell[0]} / {cell[1]}: pre {_f(stats[cell].kappa_binary)} "
            f"-> post {_f(s.kappa_binary)}"
        )
    out.append("- No branch is re-derived by code; the owner reads every value (item 6(a)).")
    return out


def _panel_section(rows: Sequence[ScoreRow], cfg: Config) -> list[str]:
    cells = _cells(rows, "panel")
    out = [
        "",
        "## Attachment-error panel (constructed; outside kappa, the gate and every rule)",
        "",
    ]
    if not cells:
        return out + ["Not scored."]
    for (v, m), rs in sorted(cells.items()):
        fails = sum(r.status == "FAIL" for r in rs)
        flagged = sum(
            r.status == "ok" and K.verdict(r.p_supported, cfg.verifier.threshold) == "UNSUPPORTED"
            for r in rs
        )
        out.append(f"- {v} / {m}: flagged {flagged} of {len(rs)} (FAIL {fails})")
    return out
