"""Which names reach the keyword table: a signal quota, not a ranking.

Every day reads only a handful of names, so the order of the lead list decides which signals
get read. M0 ordered by "earliest signal first" on ties, and X won every tie: the top 20 and
all five names were X, while a 0.95 Hugging Face model and a 2,295-star repo were never read
(docs/05 §4.2b). `order()` deals the visible slots round-robin across signals instead.

The cap is a consequence, not a clamp: when several signals have names, no signal holds more
than a fair share. When only one signal found anything, it fills the list -- dropping real
rows to satisfy a quota would be worse than a lopsided list.
"""
from __future__ import annotations

# Signal keys in the order they tend to notice a new name: the lab or the maker first, a
# sitemap echo last. Shared with report.py, which labels the blocks in this order.
EARLY = ["x", "hf", "breakout", "sitemap", "newsite", "revenue", "ask", "usecase", "cosearch", "watch"]
SLOW = {"usecase", "cosearch"}      # combo words, not names: they earn keyword rows, not a name slot


def _rank(row: dict) -> tuple:
    return (-(row.get("named") or 0), str(row.get("first_seen") or ""), row["term"])


def _primary(row: dict) -> int:
    found = [EARLY.index(k) for k in row.get("kinds", []) if k in EARLY]
    return min(found) if found else len(EARLY)


def order(rows: list[dict], limit: int = 20) -> list[dict]:
    """Every row, reordered: the first `limit` slots alternate between signals, so a name
    only one signal found cannot be crowded out by a noisier one."""
    fast = [r for r in rows if not SLOW & set(r.get("kinds", []))]
    slow = [r for r in rows if SLOW & set(r.get("kinds", []))]
    buckets: dict[int, list[dict]] = {}
    for r in fast:
        buckets.setdefault(_primary(r), []).append(r)
    for bucket in buckets.values():
        bucket.sort(key=_rank)

    picked: list[dict] = []
    while len(picked) < limit and buckets:
        moved = False
        for key in sorted(buckets):
            if buckets[key] and len(picked) < limit:
                picked.append(buckets[key].pop(0))
                moved = True
        if not moved:
            break
    taken = {id(r) for r in picked}
    rest = sorted((r for r in fast if id(r) not in taken), key=_rank)
    return picked + rest + slow
