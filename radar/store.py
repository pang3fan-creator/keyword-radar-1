"""The radar's memory: terms, their evidence and their reviews, in one SQLite file.

record()          upserts today's terms and adds one signal row per source that found them.
due()             terms old enough to check in Google Trends and not reviewed yet.
save_verdict()    hit / miss / no_data, stored as a 14-day review.
recent_sources()  X and Hugging Face terms the frequent job kept since yesterday.
summary()         hit rate and median lead per signal.
leads()           what was kept, newest first, with its review verdict.

The old `leads` table is still created and still holds the pre-M1 history, but nothing writes
it any more; scripts/migrate_leads.py copied it into these tables on 2026-10-17.
"""
from __future__ import annotations

import json
import sqlite3
import statistics
from datetime import date, timedelta
from pathlib import Path

from . import entity, select

REVIEW_DAYS = 14
SUMMARY_WINDOW = 60
SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
  term        TEXT PRIMARY KEY,
  first_seen  TEXT NOT NULL,
  last_seen   TEXT NOT NULL,
  signals     TEXT NOT NULL DEFAULT '[]',
  notes       TEXT NOT NULL DEFAULT '[]',
  named       REAL,
  variants    TEXT NOT NULL DEFAULT '[]',
  reviewed_at TEXT,
  verdict     TEXT,
  lead_days   INTEGER,
  trends      TEXT
)"""

# The long-term model (docs/05 §5). `leads` above is kept for the migrated history only.
SCHEMA_NEXT = """
CREATE TABLE IF NOT EXISTS terms (
  id            INTEGER PRIMARY KEY,
  canonical     TEXT NOT NULL UNIQUE,
  aliases       TEXT NOT NULL DEFAULT '[]',
  first_seen    TEXT NOT NULL,
  last_seen     TEXT NOT NULL,
  name_score    REAL,
  window        TEXT,
  confidence    TEXT,
  decision      TEXT,
  known         TEXT,
  status        TEXT DEFAULT 'new',
  created_at    TEXT,
  updated_at    TEXT
);
CREATE TABLE IF NOT EXISTS term_signals (
  id            INTEGER PRIMARY KEY,
  term_id       INTEGER NOT NULL REFERENCES terms(id),
  source        TEXT NOT NULL,
  source_id     TEXT,
  first_seen    TEXT NOT NULL,
  evidence      TEXT,
  url           TEXT,
  score         REAL,
  metadata      TEXT DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS keywords (
  id            INTEGER PRIMARY KEY,
  term_id       INTEGER NOT NULL REFERENCES terms(id),
  phrase        TEXT NOT NULL,
  kind          TEXT NOT NULL,
  brand         INTEGER DEFAULT 0,
  is_name       INTEGER DEFAULT 0,
  established   INTEGER DEFAULT 0,
  volume        INTEGER,
  volume_month  TEXT,
  volume_status TEXT,
  per_day       INTEGER,
  trend         TEXT DEFAULT '{}',
  competition   TEXT DEFAULT '{}',
  decision      TEXT,
  confidence    TEXT,
  created_at    TEXT,
  updated_at    TEXT
);
CREATE TABLE IF NOT EXISTS reviews (
  id            INTEGER PRIMARY KEY,
  term_id       INTEGER NOT NULL REFERENCES terms(id),
  keyword_id    INTEGER REFERENCES keywords(id),
  days          INTEGER NOT NULL,
  checked_at    TEXT NOT NULL,
  name_real     INTEGER,
  search_rise   INTEGER,
  persistence   INTEGER,
  lead_days     INTEGER,
  metrics       TEXT DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS runs (
  id            INTEGER PRIMARY KEY,
  command       TEXT NOT NULL,
  started_at    TEXT,
  finished_at   TEXT,
  cost_micros   INTEGER DEFAULT 0,
  stats         TEXT DEFAULT '{}',
  errors        TEXT DEFAULT '[]'
)"""


def connect(state_dir: Path) -> sqlite3.Connection:
    state_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(state_dir / "radar.db")
    conn.execute(SCHEMA)
    conn.executescript(SCHEMA_NEXT)
    return conn


def _note(conn: sqlite3.Connection, term_id: int) -> str | None:
    row = conn.execute("SELECT evidence FROM term_signals WHERE term_id = ? ORDER BY id DESC LIMIT 1",
                       (term_id,)).fetchone()
    return row[0] if row else None


def signals_for(conn: sqlite3.Connection, term: str) -> dict:
    """Which signals found this term and how the judge scored its name: what the leading rule
    needs when a manual `keywords` run has no lead rows of its own. A term typed as one of
    its stored spellings finds the same signals: `spark open` is `muse spark open`. The
    alias has to be one the term actually carries, not a substring of a longer name."""
    name = " ".join(term.lower().split())
    if not name:
        return {"kinds": [], "named": None}
    like = name.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    rows = conn.execute("SELECT id, canonical, name_score, aliases FROM terms"
                        " WHERE canonical = ? OR aliases LIKE ? ESCAPE '\\'",
                        (name, f'%"{like}"%')).fetchall()
    row = next((r for r in rows if r[1] == name), None) or \
        next((r for r in rows if name in json.loads(r[3])), None)
    if row is None:
        return {"kinds": [], "named": None}
    kinds = [r[0] for r in conn.execute("SELECT source FROM term_signals WHERE term_id = ? ORDER BY source",
                                        (row[0],))]
    return {"kinds": kinds, "named": row[2]}


def _term_id(conn: sqlite3.Connection, canonical: str) -> int | None:
    row = conn.execute("SELECT id FROM terms WHERE canonical = ?", (canonical,)).fetchone()
    return row[0] if row else None


def _refresh_status(conn: sqlite3.Connection, term_id: int) -> None:
    """`echo` only when every signal this term ever had is a URL listing; add a real signal and
    it becomes a name again. The status never goes from `new` back to `echo`."""
    status = conn.execute("SELECT status FROM terms WHERE id = ?", (term_id,)).fetchone()[0]
    if status not in (None, "new", "echo"):
        return                                  # watching / archived: a reviewed term keeps its state
    sources = {r[0] for r in conn.execute("SELECT source FROM term_signals WHERE term_id = ?", (term_id,))}
    wanted = "echo" if sources and sources <= select.URL_KINDS else "new"
    if wanted != status:
        conn.execute("UPDATE terms SET status = ? WHERE id = ?", (wanted, term_id))


def record(conn: sqlite3.Connection, rows: list[dict], today: date | None = None) -> int:
    """rows: report leads with term, kinds (signal names), signals (report lines),
    optional named and variants. Forms that name one thing share a term (entity.cluster),
    including a twin the migrated history stored under another spelling."""
    day = (today or date.today()).isoformat()
    prepared = [{"term": r["term"], "day": day, "source": (r.get("kinds") or [""])[0], "row": r}
                for r in rows]
    for group in entity.cluster(prepared):
        members = [m["row"] for m in group["rows"]]
        evidence: dict[str, str | None] = {}
        forms: list[str] = []
        for m in members:
            for i, kind in enumerate(m.get("kinds", [])):
                evidence.setdefault(kind, m["signals"][i] if i < len(m.get("signals", [])) else None)
            forms += [m["term"], *m.get("variants", [])]
        named = next((m["named"] for m in reversed(members) if m.get("named") is not None), None)
        canonical = group["canonical"]

        # A twin stored under another spelling is the same thing: fold it in instead of
        # adding a row that would be reviewed, and paid for, on its own.
        existing = [(tid, canonical_, aliases, score, first)
                    for tid, canonical_, aliases, score, first in
                    conn.execute("SELECT id, canonical, aliases, name_score, first_seen FROM terms")]
        matches = [e for e in existing if e[1] == canonical or entity.same_entity(canonical, e[1])]
        if matches:
            keep = min(matches, key=lambda e: (e[4], e[0]))
            for other in matches:
                if other[0] != keep[0]:
                    merge_terms(conn, keep[0], other[0])
            kept_aliases, kept_score = conn.execute(
                "SELECT aliases, name_score FROM terms WHERE id = ?", (keep[0],)).fetchone()
            aliases = sorted(set(json.loads(kept_aliases)) | set(forms) | {m[1] for m in matches})
            conn.execute("UPDATE terms SET last_seen = ?, aliases = ?, name_score = ?, updated_at = ?"
                         " WHERE id = ?",
                         (day, json.dumps(aliases, ensure_ascii=False),
                          named if named is not None else kept_score, day, keep[0]))
            term_id = keep[0]
        else:
            cur = conn.execute(
                "INSERT INTO terms (canonical, aliases, first_seen, last_seen, name_score, window,"
                " status, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (canonical, json.dumps(sorted(set(forms)), ensure_ascii=False), day, day, named,
                 select.lane(evidence), "new", day, day))
            term_id = cur.lastrowid
        for kind, note in evidence.items():
            if not conn.execute("SELECT 1 FROM term_signals WHERE term_id = ? AND source = ?",
                                (term_id, kind)).fetchone():
                conn.execute("INSERT INTO term_signals (term_id, source, first_seen, evidence)"
                             " VALUES (?,?,?,?)", (term_id, kind, day, note))
        _refresh_status(conn, term_id)
    conn.commit()
    return len(rows)

def merge_terms(conn: sqlite3.Connection, kept_id: int, drop_id: int) -> None:
    """Fold one row into another: aliases and dates widen, signals keep one row per source,
    reviews follow the term. Never drops a signal or a review."""
    kept = conn.execute("SELECT canonical, aliases, first_seen, last_seen, name_score FROM terms WHERE id = ?",
                        (kept_id,)).fetchone()
    drop = conn.execute("SELECT canonical, aliases, first_seen, last_seen, name_score FROM terms WHERE id = ?",
                        (drop_id,)).fetchone()
    aliases = sorted(set(json.loads(kept[1])) | set(json.loads(drop[1])) | {kept[0], drop[0]})
    for _id, source, first_seen, evidence in conn.execute(
            "SELECT id, source, first_seen, evidence FROM term_signals WHERE term_id = ?", (drop_id,)).fetchall():
        same = conn.execute("SELECT id, first_seen FROM term_signals WHERE term_id = ? AND source = ?",
                            (kept_id, source)).fetchone()
        if same:
            conn.execute("UPDATE term_signals SET first_seen = ? WHERE id = ?",
                         (min(same[1], first_seen), same[0]))
            conn.execute("DELETE FROM term_signals WHERE id = ?", (_id,))
        else:
            conn.execute("UPDATE term_signals SET term_id = ? WHERE id = ?", (kept_id, _id))
    for rid, days, checked in conn.execute(
            "SELECT id, days, checked_at FROM reviews WHERE term_id = ?", (drop_id,)).fetchall():
        same = conn.execute("SELECT id, checked_at FROM reviews WHERE term_id = ? AND days = ?",
                            (kept_id, days)).fetchone()
        if same is None:
            conn.execute("UPDATE reviews SET term_id = ? WHERE id = ?", (kept_id, rid))
        elif checked > same[1]:                 # one review per window; the newer reading wins whole
            conn.execute("DELETE FROM reviews WHERE id = ?", (same[0],))
            conn.execute("UPDATE reviews SET term_id = ? WHERE id = ?", (kept_id, rid))
        else:
            conn.execute("DELETE FROM reviews WHERE id = ?", (rid,))
    conn.execute("DELETE FROM terms WHERE id = ?", (drop_id,))     # free the canonical first
    conn.execute("UPDATE terms SET canonical = ?, aliases = ?, first_seen = ?, last_seen = ?,"
                 " name_score = ? WHERE id = ?",
                 (entity.canonical([kept[0], drop[0]]), json.dumps(aliases, ensure_ascii=False),
                  min(kept[2], drop[2]), max(kept[3], drop[3]),
                  kept[4] if kept[4] is not None else drop[4], kept_id))


def twins(conn: sqlite3.Connection) -> list[tuple[int, int]]:
    """(keep_id, drop_id): two rows that name one thing. The earlier row is kept."""
    rows = [(i, c, f) for i, c, f in conn.execute("SELECT id, canonical, first_seen FROM terms")]
    found = []
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            if entity.same_entity(rows[i][1], rows[j][1]):
                keep, drop = sorted((rows[i], rows[j]), key=lambda r: (r[2], r[0]))[:2]
                found.append((keep[0], drop[0]))
    return found


ECHO_WHERE = ("COALESCE(status, 'new') != 'echo' AND id IN (SELECT term_id FROM term_signals"
              " GROUP BY term_id HAVING SUM(source NOT IN ('sitemap', 'newsite')) = 0)")


def echo_ids(conn: sqlite3.Connection) -> list[int]:
    """Terms that only a sitemap or a new-site listing found: an echo of a name that already
    exists (bitbucket, zotero), not a new word."""
    return [r[0] for r in conn.execute(f"SELECT id FROM terms WHERE {ECHO_WHERE}")]


def mark_echoes(conn: sqlite3.Connection) -> int:
    """Keep the echo rows, but never spend a Trends review on one."""
    cur = conn.execute(f"UPDATE terms SET status = 'echo' WHERE {ECHO_WHERE}")
    conn.commit()
    return cur.rowcount


def record_run(conn: sqlite3.Connection, command: str, started_at: str, finished_at: str,
               cost_micros: int, stats: dict, errors: list[str]) -> int:
    """The day's money and outcome, so the budget can be read instead of remembered."""
    cur = conn.execute("INSERT INTO runs (command, started_at, finished_at, cost_micros, stats, errors)"
                       " VALUES (?,?,?,?,?,?)",
                       (command, started_at, finished_at, cost_micros, json.dumps(stats, ensure_ascii=False),
                        json.dumps(errors, ensure_ascii=False)))
    conn.commit()
    return cur.lastrowid


def due(conn: sqlite3.Connection, today: date, after_days: int, limit: int) -> list[tuple[str, date, list[str]]]:
    cutoff = (today - timedelta(days=after_days)).isoformat()
    rows = conn.execute(
        "SELECT canonical, first_seen, aliases FROM terms t WHERE first_seen <= ?"
        " AND COALESCE(t.status, 'new') != 'echo' AND NOT EXISTS"
        " (SELECT 1 FROM reviews r WHERE r.term_id = t.id AND r.days = ?)"
        " ORDER BY first_seen, canonical LIMIT ?", (cutoff, REVIEW_DAYS, limit)).fetchall()
    return [(t, date.fromisoformat(f), json.loads(a)) for t, f, a in rows]


def save_verdict(conn: sqlite3.Connection, term: str, verdict: str, lead_days: int | None, trends: dict,
                 today: date | None = None) -> None:
    term_id = _term_id(conn, term)
    if term_id is None:
        return
    day = (today or date.today()).isoformat()
    metrics = json.dumps({**trends, "verdict": verdict}, ensure_ascii=False)
    rise = {"hit": 1, "miss": 0}.get(verdict)
    found = conn.execute("SELECT id FROM reviews WHERE term_id = ? AND days = ?",
                         (term_id, REVIEW_DAYS)).fetchone()
    if found:
        conn.execute("UPDATE reviews SET checked_at = ?, search_rise = ?, lead_days = ?, metrics = ?"
                     " WHERE id = ?", (day, rise, lead_days, metrics, found[0]))
    else:
        conn.execute("INSERT INTO reviews (term_id, days, checked_at, search_rise, lead_days, metrics)"
                     " VALUES (?,?,?,?,?,?)", (term_id, REVIEW_DAYS, day, rise, lead_days, metrics))
    conn.execute("UPDATE terms SET status = 'watching', updated_at = ? WHERE id = ?", (day, term_id))
    conn.commit()


def recent_sources(conn: sqlite3.Connection, today: date | None = None) -> list[dict]:
    since = ((today or date.today()) - timedelta(days=1)).isoformat()
    rows = conn.execute(
        "SELECT t.id, t.canonical, group_concat(DISTINCT s.source), t.name_score FROM terms t"
        " JOIN term_signals s ON s.term_id = t.id"
        " WHERE t.last_seen >= ? AND s.source IN ('x', 'hf')"
        " GROUP BY t.id ORDER BY t.last_seen DESC, t.canonical", (since,)).fetchall()
    out = [{"term": term, "kinds": sorted(kinds.split(",")), "named": score, "note": _note(conn, tid)}
           for tid, term, kinds, score in rows]
    return [r for r in out if {"x", "hf"} & set(r["kinds"])][:20]


def summary(conn: sqlite3.Connection, today: date | None = None) -> dict:
    since = ((today or date.today()) - timedelta(days=SUMMARY_WINDOW)).isoformat()
    rows = conn.execute(
        "SELECT s.source, r.search_rise, r.lead_days FROM term_signals s"
        " JOIN terms t ON t.id = s.term_id"
        " JOIN reviews r ON r.term_id = t.id AND r.days = ?"
        " WHERE r.checked_at >= ?", (REVIEW_DAYS, since)).fetchall()
    by: dict[str, dict] = {}
    for source, rise, lead in rows:
        s = by.setdefault(source, {"checked": 0, "hit": 0, "leads": []})
        s["checked"] += 1
        if rise == 1:
            s["hit"] += 1
            s["leads"].append(lead)
    for s in by.values():
        leads = s.pop("leads")
        s["median_lead"] = statistics.median(leads) if leads else None
    pending = conn.execute("SELECT count(*) FROM terms t WHERE COALESCE(t.status, 'new') != 'echo'"
                           " AND NOT EXISTS (SELECT 1 FROM reviews r WHERE r.term_id = t.id AND r.days = ?)",
                           (REVIEW_DAYS,)).fetchone()[0]
    return {"by_signal": by, "pending": pending, "window_days": SUMMARY_WINDOW}


def leads(conn: sqlite3.Connection, days: int = 7, today: date | None = None) -> list[dict]:
    """Leads seen in the last `days` days, newest first, with their review verdict when there is one."""
    day = (today or date.today()).isoformat()
    since = ((today or date.today()) - timedelta(days=days)).isoformat()
    rows = conn.execute(
        "SELECT t.id, t.canonical, t.first_seen, t.last_seen, group_concat(DISTINCT s.source),"
        " t.name_score, t.aliases, r.metrics, r.lead_days FROM terms t"
        " LEFT JOIN term_signals s ON s.term_id = t.id"
        " LEFT JOIN reviews r ON r.term_id = t.id AND r.days = ?"
        " WHERE t.last_seen >= ? GROUP BY t.id"
        " ORDER BY t.last_seen DESC, t.first_seen DESC, t.canonical", (REVIEW_DAYS, since)).fetchall()
    return [{"term": term, "first_seen": f, "last_seen": l,
             "signals": sorted(kinds.split(",")) if kinds else [],
             "note": _note(conn, tid), "name_score": named, "variants": json.loads(aliases),
             "verdict": json.loads(metrics or "{}").get("verdict"), "days_ahead": ahead,
             "new": f == day}                     # new by when we first saw it, not by a Trends baseline
            for tid, term, f, l, kinds, named, aliases, metrics, ahead in rows]
