"""Git checks that turn T6's ordering rules into code guards (D-044 items 3, 4, 7, 9, 10).

"Committed" means: tracked by git and identical to HEAD. Every check takes an injectable runner so
the tests stub git instead of touching the repository."""

from __future__ import annotations

import hashlib
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path

Runner = Callable[[Sequence[str]], subprocess.CompletedProcess]


def _run(args: Sequence[str]) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=False)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def is_tracked(path: Path, run: Runner = _run) -> bool:
    return run(["ls-files", "--error-unmatch", "--", Path(path).as_posix()]).returncode == 0


def is_committed(path: Path, run: Runner = _run) -> bool:
    """Tracked, and the working-tree file equals HEAD's."""
    p = Path(path).as_posix()
    return is_tracked(path, run) and run(["diff", "--quiet", "HEAD", "--", p]).returncode == 0


def head_text(path: Path, run: Runner = _run) -> str | None:
    """The file as committed at HEAD, or None."""
    res = run(["show", f"HEAD:{Path(path).as_posix()}"])
    return res.stdout if res.returncode == 0 else None


def head_commit(run: Runner = _run) -> str:
    return run(["rev-parse", "HEAD"]).stdout.strip()


def dirty(run: Runner = _run, untracked_under: Sequence[str] = ()) -> list[str]:
    """Modified tracked files, plus untracked files under ``untracked_under``."""
    out = run(["status", "--porcelain", "--untracked-files=all"]).stdout.splitlines()
    found = []
    for line in out:
        code, path = line[:2], line[3:].strip().strip('"')
        if code == "??":
            if any(path.startswith(d.rstrip("/") + "/") for d in untracked_under):
                found.append(path)
        else:
            found.append(path)
    return found
