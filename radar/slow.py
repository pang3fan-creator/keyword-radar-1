"""The slow lane: combo words once a week, measured by the fast lane's own chain.

Seeds are `slow.objects` x `slow.actions`; Autocomplete expands them for free. The
candidates then take the same labels and decision as a fast lead -- Google Ads volume,
Trends shape, searches a day, page one -- so the radar keeps one judge, not two.

The output is its own report and its own rows (`terms.window='slow'`). A slow word never
takes a visible name slot, one of the five daily reads, or a place in the 14-day review:
`select.SLOW` keeps it out of the first two, `store.due()` out of the third.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from . import autocomplete, competition, config, store, usecases

RANK = {"prioritize": 0, "watch": 1, "skip": 2}


def balance(rows: list[dict], per_category: int = 8, synonyms: int = 3) -> list[dict]:
    """Keep the strongest rows per category (object), and at most `synonyms` near-copies of
    a phrase in one category: "ai headshot generator free/online/app/cheap" is one idea."""
    out: list[dict] = []
    count: dict[str, int] = {}
    kept: dict[str, list[str]] = {}
    for r in sorted(rows, key=lambda r: (RANK.get(r.get("decision"), 9), -(r.get("per_day") or 0),
                                         -(r.get("volume") or 0), r["term"])):
        cat = (r.get("objects") or [""])[0]
        if count.get(cat, 0) >= per_category:
            continue
        words = set(r["term"].split())
        if sum(1 for k in kept.get(cat, []) if len(words & set(k.split())) >= 2) >= synonyms:
            continue
        count[cat] = count.get(cat, 0) + 1
        kept.setdefault(cat, []).append(r["term"])
        out.append(r)
    return out


def spread(rows: list[dict], cap: int) -> list[dict]:
    """Up to `cap` rows, dealt round-robin across categories: an alphabetical cap would read
    the avatar terms and never the watermark ones."""
    by: dict[str, list[dict]] = {}
    for r in sorted(rows, key=lambda r: (-r["found_by"], r["term"])):
        by.setdefault((r.get("objects") or [""])[0], []).append(r)
    out: list[dict] = []
    while len(out) < cap and any(by.values()):
        for key in sorted(by):
            if by[key] and len(out) < cap:
                out.append(by[key].pop(0))
    return out


def _existing(state: Path) -> dict[str, str]:
    return {canon: first for canon, first in
            store.connect(state).execute("SELECT canonical, first_seen FROM terms")}


def run(cfg: dict, state: Path, today: date | None = None, paid: bool = True) -> dict:
    c = cfg["slow"]
    today = today or date.today()
    seeds = autocomplete.seeds(cfg)
    cands, errors = autocomplete.candidates(seeds, lambda term: config.known(cfg, term), cfg)
    seen = _existing(state)
    rows = [{"term": x["term"], "phrase": x["term"], "kind": "generic", "objects": x["objects"],
             "brand": False, "found_by": len(x["seeds"]), "evidence": f"autocomplete: {x['seeds'][0]}",
             "first_seen": seen.get(x["term"], today.isoformat()), "fresh": x["term"] not in seen}
            for x in cands]
    base = {"seeds": len(seeds), "queries": min(len(seeds), c["max_queries"]), "candidates": len(cands),
            "paid": paid, "errors": errors}
    if not paid:
        return {**base, "rows": spread(rows, c["max_rows"]),
                "cost_micros": 0, "spend": {}, "paid_errors": [], "asked_volumes": 0, "asked_trends": 0}
    if not rows:
        return {**base, "rows": [], "cost_micros": 0, "spend": {}, "paid_errors": [],
                "asked_volumes": 0, "asked_trends": 0}

    cost, paid_errors = 0, []
    spend = {"volumes": 0, "trends": 0, "page_one": 0}
    rows = spread(rows, c["max_volumes"])
    asked_volumes = len(rows)
    vol, spent = usecases.volumes([r["phrase"] for r in rows], cfg["usecases"]["location_code"])
    cost += spent
    spend["volumes"] = spent
    sized = usecases.keep({r["phrase"]: r for r in rows}, vol, c)      # min_volume is a label, not a gate
    solo: dict[str, list] = {}
    try:
        solo, spent = usecases.solo_series([r["phrase"] for r in sized[:c["trends_max"]]], today)
        cost += spent
        spend["trends"] = spent
    except Exception as exc:  # noqa: BLE001  the table still prints, without a shape
        paid_errors.append(f"trends: {exc}")
    usecases.measure(sized, solo, {}, c["min_daily"], today, {}, {})
    try:
        comp = {**cfg, "competition": {**cfg["competition"], "max_rows": c["page_one"]}}
        spent, comp_errors = competition.assess(sized, comp, state)
        cost += spent
        spend["page_one"] = spent
        paid_errors += comp_errors
    except Exception as exc:  # noqa: BLE001
        paid_errors.append(f"page one: {exc}")
    rows = balance(sized, c["per_category"], c["synonyms"])[:c["max_rows"]]
    if rows:
        store.record(store.connect(state),
                     [{"term": r["term"], "kinds": ["autocomplete"], "signals": [r["evidence"]],
                       "named": None, "variants": []} for r in rows], today=today)
    return {**base, "rows": rows, "cost_micros": cost, "spend": spend, "paid_errors": paid_errors,
            "asked_volumes": asked_volumes, "asked_trends": len(solo)}
