"""Signal ⑨: Show HN, where a tool is named on the day it ships.

Hacker News' public Algolia index (no key): Show HN stories from the last `lookback_hours`
with at least `min_points`. A title is a near-perfect carrier for a name -- "Show HN: Fable
- a writing app" -- so the leading capitalised run of the title, before the first dash,
colon or bracket, is the name. The point floor drops the showcase posts nobody upvoted;
a story that crosses it later is still new, because a skipped story is not marked seen.

Each story is reported once: objectIDs live in state/hn_seen.json.gz. A name that two
stories carry is one lead with both examples. A full Algolia page is reported as capped:
the tail was not read, and saying so beats a silent limit.
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import UA, entity, snap
from .i18n import t

URL = "https://hn.algolia.com/api/v1/search_by_date"
SEEN_DAYS = 60
HITS = 100        # Algolia page size; a full page means the tail was not read

PREFIX = "show hn:"
NOT_A_NAME = ("ask hn:", "tell hn:", "poll:", "launch hn:")
# A name ends at the first separator: "Open Scrantic - Johnny Castaway", "Fable (a writing app)".
SEP = re.compile(r"\s+[–—|]\s+|\s+-\s+|\s*\(|\s*:\s")
# The part before it has to start like a name: a capital or a digit, up to three words.
LEAD = re.compile(r"^[A-Z0-9][\w.+'-]*(?:\s+[A-Z0-9][\w.+'-]*){0,2}")
GENERIC = {"the", "a", "an", "i", "we", "my", "our", "show", "hn", "ask", "tell", "new", "app",
           "tool", "site", "demo", "beta", "launch", "update", "project"}


def title_name(title: str) -> str | None:
    """'Show HN: Open Scrantic - Johnny Castaway' -> 'open scrantic'; a title that names no
    thing ('Show HN: I built a tiny tool') -> None."""
    text = title.strip()
    low = text.lower()
    if low.startswith(NOT_A_NAME):
        return None
    if low.startswith(PREFIX):
        text = text[len(PREFIX):].strip()
    part = SEP.split(text, maxsplit=1)[0].strip(" .,!?:;-–—'")
    match = LEAD.match(part)
    if not match:
        return None
    name = " ".join(match.group(0).lower().split())
    words = name.split()
    if len(name) < 3 or all(w in GENERIC for w in words) or words[0] in {"i", "we", "my", "our", "the", "a", "an"}:
        return None
    if name in entity.MAKERS and not any(ch.isdigit() for ch in name):
        return None     # "OpenAI" is a company, not this week's new name
    if len(words) == 1 and len(name) >= 6 and name.endswith("ing"):
        return None     # "Show HN: Building an LLM from Scratch" is a gerund, not a name
    return name


def _url(cfg, now: datetime) -> str:
    since = int((now - timedelta(hours=cfg["hn"]["lookback_hours"])).timestamp())
    query = urllib.parse.urlencode({"tags": "show_hn", "hitsPerPage": HITS,
                                    "numericFilters": f"points>={cfg['hn']['min_points']},created_at_i>={since}"})
    return f"{URL}?{query}"


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as res:
        return json.load(res)


def hn(cfg: dict, state: Path, now: datetime | None = None) -> dict:
    c = cfg["hn"]
    now = now or datetime.now(timezone.utc)
    hits = _get(_url(cfg, now)).get("hits") or []
    path = state / "hn_seen.json.gz"
    seen: dict[str, str] = snap.load(path) or {}
    today = now.date().isoformat()
    rows: dict[str, dict] = {}
    for h in hits:
        if h["objectID"] in seen or int(h.get("points") or 0) < c["min_points"]:
            continue
        name = title_name(h.get("title") or "")
        if not name:
            continue
        row = rows.setdefault(name, {"term": name, "recent": 0, "points": 0, "comments": 0, "examples": []})
        row["recent"] += 1
        row["points"] = max(row["points"], int(h.get("points") or 0))
        row["comments"] = max(row["comments"], int(h.get("num_comments") or 0))
        row["examples"].append(h.get("title") or "")
        seen[h["objectID"]] = today
    out = sorted(rows.values(), key=lambda r: (-r["points"], r["term"]))[:c["top"]]
    for r in out:
        r["note"] = t("note_hn", points=r["points"], comments=r["comments"])
    if hits:        # a failed fetch keeps yesterday's snapshot
        cutoff = (now - timedelta(days=SEEN_DAYS)).date().isoformat()
        snap.save(path, {k: v for k, v in seen.items() if v >= cutoff})
    return {"read": len(hits), "found": len(out), "capped": len(hits) >= HITS, "terms": out}
