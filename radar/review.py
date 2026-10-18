"""The radar's review: read a term at more than one window after it was first seen.

A fast-lane term is read at 1d, 3d, 7d and 14d; a slow-lane word at 14d and 30d. The first two
are local and free: name_real (does the name judge stand behind it) and persistence (was it
seen again after first_seen). The Trends windows share one series per lane: the final one is
the paid request (14d fast, 30d slow), and the earlier reading is that series cut at its own
horizon. Two paid checks per term would cost twice and ask the same question; this answers
"did it rise in its first week" and "did it rise by the end" from the same data.

Each variant is its own call: in one shared task the values share a 0-100 scale and a small
term next to a big one reads 0, and the live endpoint runs only the first task of a request's
body, so tasks cannot be batched into one call either. A variant "rose" when its peak after
first_seen clears its own baseline (the mean before first_seen) by RISE_FACTOR and RISE_MIN;
a word with an older meaning ("strata": strata rock, strata title) has a high baseline and
does not rise, while "niko1221 strata" goes from 0 to something.

This is verification, not discovery: it tells you which signals to trust.
"""
from __future__ import annotations

import sqlite3
import statistics
from datetime import date, timedelta

from . import aisa, store

BEFORE_DAYS = 30
MAX_VARIANTS = 3      # each costs one Trends task ($0.0012 in October 2026)
RISE_FACTOR, RISE_MIN = 2.0, 10
RISE_SHARE = 0.25     # the rise starts where a series first covers this share of base -> peak
TOOL = "post_dataforseo_keywords_trends_explore_live"
# Google has not settled the last two days of a daily series: they come back as 0 and
# then 100 for unrelated terms ("ai image detector": ..., 5, 5, 0, 100 on 2026-10-12),
# which reads as a rise. Every reader drops them (settled()).
UNSETTLED_DAYS = 2
# A window shorter than this cannot come from Trends: the last two days are unsettled, so a
# 24h or 72h reading would be mostly missing. Those windows are local (name_real, persistence).
TRENDS_FROM = 7


def settled(points: list[tuple], today: date) -> list[tuple]:
    """A daily Trends series without its last UNSETTLED_DAYS days. Rows are (day, value, ...)."""
    cut = today - timedelta(days=UNSETTLED_DAYS)
    return [p for p in points if p[0] < cut]


def rose(points: list[tuple[date, int]], first_seen: date) -> dict:
    """One variant's Trends series judged against its own baseline."""
    values = [v for _, v in points]
    if not values or max(values) == 0:
        return {"rose": False, "no_data": True}
    before = [v for d, v in points if d < first_seen]
    after = [v for d, v in points if d >= first_seen]
    base = statistics.mean(before) if before else 0.0
    peak_after = max(after, default=0)
    peak = max(values)
    out = {"base": round(base, 1), "peak_after": peak_after, "no_data": False,
           "rose": peak_after >= max(base * RISE_FACTOR, base + RISE_MIN)}
    if out["rose"]:
        line = base + RISE_SHARE * (peak - base)
        out["first_rise"] = next(d for d, v in points if v >= max(line, 1) and v > base).isoformat()
    return out


def verdict(per_variant: dict[str, dict], first_seen: date) -> tuple[str, int | None]:
    risen = [v for v in per_variant.values() if v.get("rose")]
    if risen:
        first = min(date.fromisoformat(v["first_rise"]) for v in risen)
        return "hit", (first - first_seen).days
    if all(v.get("no_data") for v in per_variant.values()):
        return "no_data", None
    return "miss", None


def _series(task: dict) -> list[tuple[date, int]]:
    try:
        item = task["result"][0]["items"][0]
    except (KeyError, IndexError, TypeError):
        return []
    return [(date.fromisoformat(p["date_from"]), int((p.get("values") or [0])[0] or 0)) for p in item.get("data", [])]


def plan_calls(due: list[tuple], today: date, horizon: int = 14) -> tuple[list[dict], list[tuple]]:
    """One Trends call per search variant of each due lead, over its review window. The window
    ends at first_seen + horizon even when the check runs later: a late 7-day reading still
    says what happened in the first week, not what happened by the day it was read."""
    calls, plan = [], []
    for i, (term, first_seen, variants) in enumerate(due):
        keys = (list(variants) or [term])[:MAX_VARIANTS]
        window = {"date_from": (first_seen - timedelta(days=BEFORE_DAYS)).isoformat(),
                  "date_to": min(first_seen + timedelta(days=horizon), today).isoformat()}
        ids = [f"r{i}v{j}" for j in range(len(keys))]
        calls += [{"call_id": cid, "tool": TOOL, "arguments": {"body": [{"keywords": [k], **window}]}}
                  for cid, k in zip(ids, keys)]
        plan.append((ids, term, first_seen, keys))
    return calls, plan


def _local(cfg: dict, term: str, first_seen: date, facts: dict, today: date) -> dict:
    """The free reading: the judge's strong bar, and whether the term was seen on a later day."""
    score = facts.get("name_score")
    last = facts.get("last_seen")
    return {"name_real": None if score is None else int(score >= cfg["review"]["name_real_score"]),
            "persistence": int(bool(last) and last > first_seen.isoformat()),
            "metrics": {"score": score, "sources": facts.get("sources", 0), "last_seen": last,
                        "age_days": (today - first_seen).days}}


def _free(cfg: dict, conn: sqlite3.Connection, today: date, lane: str, days_list: tuple) -> list[dict]:
    """The 1d and 3d windows: local evidence only, so they are never sampled by a budget."""
    checked = []
    for days in days_list:
        if days >= TRENDS_FROM:
            continue
        due = store.due(conn, today, days, None, lane)
        if not due:
            continue
        facts = store.review_facts(conn, [t for t, _, _ in due])
        for term, first_seen, _ in due:
            row = _local(cfg, term, first_seen, facts.get(term, {}), today)
            store.save_review(conn, term, days, today, name_real=row["name_real"],
                              persistence=row["persistence"], metrics=row["metrics"])
            checked.append({"term": term, "days": days, "lane": lane,
                            "first_seen": first_seen.isoformat(), "name_real": row["name_real"],
                            "persistence": row["persistence"], "search_rise": None, "lead_days": None,
                            "age_days": (today - first_seen).days})
    return checked


def _paid(cfg: dict, conn: sqlite3.Connection, today: date, lane: str, days_list: tuple,
          errors: list[str]) -> tuple[list[dict], int]:
    """The Trends windows of one lane: one series per variant, read at every horizon."""
    final = days_list[-1]
    horizons = [d for d in days_list if d >= TRENDS_FROM]
    if not horizons:                            # a lane of free windows only: no Trends call
        return [], 0
    due = store.due(conn, today, final, cfg["review"]["per_day"], lane)
    if not due:
        return [], 0
    calls, plan = plan_calls(due, today, final)
    try:
        data, cost = aisa.call_all(calls)
    except aisa.AisaError as exc:
        errors.append(f"{lane} {final}d: {exc}")      # the other lane still gets its check
        return [], 0
    facts = store.review_facts(conn, [term for _, term, _, _ in plan])
    checked = []
    for ids, term, first_seen, keys in plan:
        if not all(cid in data for cid in ids):
            errors.append(f"{term}: no Trends answer at {final}d")   # stays due, no row
            continue
        series = {k: settled(_series((data[cid].get("tasks") or [{}])[0]), today)
                  for cid, k in zip(ids, keys)}
        local = _local(cfg, term, first_seen, facts.get(term, {}), today) if lane == "fast" else None
        for days in horizons:
            per = {k: rose([p for p in series[k] if p[0] <= first_seen + timedelta(days=days)], first_seen)
                   for k in keys}
            v, lead = verdict(per, first_seen)
            rise = {"hit": 1, "miss": 0}.get(v)
            store.save_review(conn, term, days, today,
                              name_real=local["name_real"] if local else None,
                              persistence=local["persistence"] if local else None,
                              search_rise=rise, lead_days=lead,
                              metrics={"per": per, "verdict": v,
                                       "window_from": (first_seen - timedelta(days=BEFORE_DAYS)).isoformat(),
                                       "window_to": (first_seen + timedelta(days=days)).isoformat(),
                                       "checked_at": today.isoformat()},
                              final=(days == final))
            checked.append({"term": term, "days": days, "lane": lane, "first_seen": first_seen.isoformat(),
                            "name_real": local["name_real"] if local else None,
                            "persistence": local["persistence"] if local else None,
                            "search_rise": rise, "lead_days": lead})
    return checked, cost


def review(cfg: dict, conn: sqlite3.Connection, today: date | None = None) -> dict:
    today = today or date.today()
    windows = {lane: tuple(days) for lane, days in cfg["review"]["windows"].items()}
    checked: list[dict] = []
    errors: list[str] = []
    cost = 0
    for lane, days_list in windows.items():
        checked += _free(cfg, conn, today, lane, days_list)
    for lane, days_list in windows.items():
        rows, spent = _paid(cfg, conn, today, lane, days_list, errors)
        checked += rows
        cost += spent
    next_paid = {}
    for lane, days_list in windows.items():
        when = store.next_due(conn, today, days_list[-1], lane)
        next_paid[lane] = when.isoformat() if when else None
    return {"checked": checked, "cost_micros": cost, "errors": errors, "next_paid": next_paid}
