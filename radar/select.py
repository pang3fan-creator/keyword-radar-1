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
EARLY = ["official", "x", "hf", "breakout", "hn", "ph", "sitemap", "newsite", "revenue", "ask", "usecase",
         "cosearch", "autocomplete", "watch"]
SLOW = {"usecase", "cosearch", "autocomplete"}   # combo words, not names: no name slot, no five-name read
URL_KINDS = {"sitemap", "newsite"}  # a competitor publishing a page is an echo of a name, not a new one
QUOTA = 0.6                         # no signal should hold more than this share of the visible names


def lane(kinds) -> str | None:
    """Which lane found it: an event source names a thing today, a combo phrase shows up over
    weeks. `ask` sits on the fast side for now; docs/05 §3.1 puts the help signal on a weekly
    P2, so it may move to the slow side once the quota has seen real data."""
    kinds = set(kinds)
    if not kinds:
        return None
    return "slow" if kinds <= SLOW else "fast"


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


def quota_note(rows: list[dict], limit: int = 20) -> tuple[str, int, int] | None:
    """Which signal swallowed the visible names, when one did. A quota that never applied
    because only one signal had names is not a bug, but it must not pass in silence: a day
    like that is the day the radar reads one kind of lead and calls it discovery."""
    top = rows[:limit]
    if not top:
        return None
    counts: dict[str, int] = {}
    for r in top:
        counts[EARLY[_primary(r)]] = counts.get(EARLY[_primary(r)], 0) + 1
    signal, count = max(counts.items(), key=lambda kv: kv[1])
    return (signal, count, len(top)) if count > QUOTA * len(top) else None
