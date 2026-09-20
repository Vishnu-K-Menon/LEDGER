"""Seeded, stratified draws (D-034). Same seed -> identical draw; inputs are sorted before
sampling so the result does not depend on listing order."""

from __future__ import annotations

import random
from collections.abc import Callable, Hashable, Iterable, Sequence


def seeded(seed: int, salt: str) -> random.Random:
    """One independent RNG per source so adding a source never shifts another's draw."""
    return random.Random(f"{seed}:{salt}")


def draw[T](
    items: Sequence[T], n: int, rng: random.Random, key: Callable[[T], Hashable]
) -> list[T]:
    pool = sorted(items, key=key)
    if n >= len(pool):
        return pool
    return rng.sample(pool, n)


def draw_stratified[T](
    items: Iterable[T],
    per_stratum: int,
    rng: random.Random,
    *,
    stratum: Callable[[T], Hashable],
    key: Callable[[T], Hashable],
) -> list[T]:
    groups: dict[Hashable, list[T]] = {}
    for it in items:
        groups.setdefault(stratum(it), []).append(it)
    out: list[T] = []
    for s in sorted(groups, key=str):
        out.extend(draw(groups[s], per_stratum, rng, key))
    return out
