"""One-off migration: the old `leads` table into terms / term_signals / reviews / runs.

The old table stays where it is and keeps being written by `daily` until M1 moves the
readers over. migrate() only adds rows, skips a term it has already copied, and can be
re-run after a daily run brought in new leads. docs/05 §5.1 is the mapping.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from . import store

# Which lane a signal belongs to (docs/05 §1): an event source names a new thing today;
# a use-case or co-search phrase is a combo word that shows up over weeks. "ask" is the
# open question: docs/05 §3.1 puts the help signal on a weekly P2, so it may belong on the
# slow side; the migrated rows have no ask-only lead, so nothing depends on it yet.
FAST_KINDS = {"x", "hf", "breakout", "sitemap", "newsite", "revenue", "ask", "watch"}
SLOW_KINDS = {"usecase", "cosearch"}
REVIEW_DAYS = 14


def _window(kinds: list[str]) -> str | None:
    if set(kinds) & FAST_KINDS:
        return "fast"
    if set(kinds) & SLOW_KINDS:
        return "slow"
    return None


def _search_rise(verdict: str | None) -> int | None:
    return {"hit": 1, "miss": 0}.get(verdict or "")


def migrate(conn, today: date | None = None, dry_run: bool = False) -> dict:
    """Copy every lead once. Returns the counts; with dry_run the rows are rolled back."""
    conn.executescript(store.SCHEMA_NEXT)
    conn.commit()
    stats = {"terms": 0, "signals": 0, "reviews": 0, "skipped": 0}
    rows = conn.execute("SELECT term, first_seen, last_seen, signals, notes, named, variants,"
                        " reviewed_at, verdict, lead_days, trends FROM leads ORDER BY term").fetchall()
    for term, first, last, signals, notes, named, variants, reviewed_at, verdict, lead_days, trends in rows:
        if conn.execute("SELECT 1 FROM terms WHERE canonical = ?", (term,)).fetchone():
            stats["skipped"] += 1
            continue
        kinds = json.loads(signals) or []
        note_list = json.loads(notes) or []
        evidence = note_list[-1] if note_list else None
        cur = conn.execute(
            "INSERT INTO terms (canonical, aliases, first_seen, last_seen, name_score, window,"
            " status, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (term, json.dumps(json.loads(variants) or [], ensure_ascii=False), first, last, named,
             _window(kinds), "new", first, last))
        stats["terms"] += 1
        for kind in sorted(set(kinds)):
            conn.execute("INSERT INTO term_signals (term_id, source, first_seen, evidence)"
                         " VALUES (?,?,?,?)", (cur.lastrowid, kind, first, evidence))
            stats["signals"] += 1
        if reviewed_at:
            metrics = {**json.loads(trends or "{}"), "verdict": verdict}
            conn.execute("INSERT INTO reviews (term_id, days, checked_at, search_rise, lead_days, metrics)"
                         " VALUES (?,?,?,?,?,?)",
                         (cur.lastrowid, REVIEW_DAYS, reviewed_at, _search_rise(verdict), lead_days,
                          json.dumps(metrics, ensure_ascii=False)))
            stats["reviews"] += 1
    if dry_run:
        conn.rollback()
    else:
        conn.commit()
    return stats


def reconcile(conn) -> dict:
    """Compare the old table with the new one: what arrived, what did not, what changed."""
    leads = {r[0] for r in conn.execute("SELECT term FROM leads")}
    terms = {r[0] for r in conn.execute("SELECT canonical FROM terms")}
    drift = conn.execute(
        "SELECT count(*) FROM leads l JOIN terms t ON t.canonical = l.term"
        " WHERE t.first_seen != l.first_seen OR t.last_seen != l.last_seen"
        " OR IFNULL(t.name_score, -1) != IFNULL(l.named, -1) OR t.aliases != l.variants"
    ).fetchone()[0]
    return {"leads": len(leads), "terms": len(terms), "missing": sorted(leads - terms),
            "drift": drift,
            "signals": conn.execute("SELECT count(*) FROM term_signals").fetchone()[0],
            "reviews": conn.execute("SELECT count(*) FROM reviews").fetchone()[0]}


def read_report(path: Path) -> dict:
    """The parts of a finished run's report.json worth keeping as a calibration reference."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {"leads": len(data.get("leads") or []), "keywords": len(data.get("keywords") or []),
            "pending": (data.get("summary") or {}).get("pending")}


def add_run(conn, started_at: str, command: str, cost_micros: int | None = None,
            stats: dict | None = None) -> int:
    """Record a historical run once; returns 0 when it is already there."""
    if conn.execute("SELECT 1 FROM runs WHERE command = ? AND started_at = ?",
                    (command, started_at)).fetchone():
        return 0
    cur = conn.execute("INSERT INTO runs (command, started_at, finished_at, cost_micros, stats)"
                       " VALUES (?,?,?,?,?)",
                       (command, started_at, started_at, cost_micros,
                        json.dumps(stats or {}, ensure_ascii=False)))
    conn.commit()
    return cur.lastrowid
