"""Signal ⑩: Product Hunt, where a tool is launched with a tagline and the day's votes.

The API is GraphQL. Public read needs a developer token from the dashboard, kept in
`PH_API_KEY` (the key+secret client flow is for apps acting for a user and is not needed
here). One query per run asks for the posts of the last `ph.lookback_hours` in the AI topic,
ordered by votes; a post below `ph.min_votes` is not a launch worth reading, and is not
marked seen, so one that climbs later is still new.

A product is reported once (state/ph_seen.json.gz). The name is the post's name before its
subtitle and the first word after the colon that is not filler ("Notion: Context for your
agents" -> `notion context`), and before " by <maker>"; the tagline is what the name judge
reads. A maker alone relaunching is not a new name.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import UA, entity, snap
from .i18n import t

URL = "https://api.producthunt.com/v2/api/graphql"
READ_MAX = 50       # posts asked for; a full page means the tail was not read
SEEN_DAYS = 60
QUERY = """query ($after: DateTime!, $topic: String!) {
  posts(first: %d, order: VOTES, postedAfter: $after, topic: $topic) {
    edges { node { id name tagline votesCount url } }
  }
}""" % READ_MAX


# Words that introduce a tagline instead of naming its feature: "Notion: for your agents",
# "Notion: The agents", "Notion: Introducing Agents". The scan stops after PAIR_WORDS, so a
# sentence ("Linear: How we built the issue tracker") keeps the brand alone.
BLOCK = {"the", "a", "an", "for", "with", "your", "our", "how", "why", "what", "when", "now",
         "new", "introducing", "introduce", "launching", "launch", "released", "release",
         "we", "i", "you", "it", "they", "is", "are", "was", "were", "built", "build", "made", "make"}
PAIR_WORDS = 3


def name(raw: str) -> str:
    """'Notion: Context for your agents' -> 'notion context' (the feature, not the decade-old
    brand); 'Notion: for your agents' -> 'notion agents'; 'GPU Terminal by Context.dev' ->
    'gpu terminal'. Only a one-word brand is paired, and only with the first word after the
    colon that is not filler: 'Foo: Bar: Baz' stays 'foo bar'."""
    parts = [p.strip() for p in raw.split(":") if p.strip()]
    if not parts:
        return ""
    head = parts[0]
    if len(parts) > 1 and len(head.split()) == 1:
        for word in parts[1].split()[:PAIR_WORDS]:
            if word.lower().strip(",.") not in BLOCK:
                head = f"{head} {word}"       # the part before ':' alone is usually a brand
                break
    text = re.split(r"\s+by\s+", head)[0]
    return " ".join(text.lower().split())


def _graphql(query: str, variables: dict) -> dict:
    token = os.environ.get("PH_API_KEY")
    if not token:
        raise RuntimeError("no PH_API_KEY")
    req = urllib.request.Request(URL, data=json.dumps({"query": query, "variables": variables}).encode(),
                                 method="POST", headers={
                                     "Content-Type": "application/json", "Accept": "application/json",
                                     "Authorization": f"Bearer {token}", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            body = json.load(res)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code}: {exc.read()[:160].decode('utf-8', 'replace')}") from exc
    if body.get("errors"):
        raise RuntimeError(str(body["errors"])[:200])
    return body.get("data") or {}


def ph(cfg: dict, state: Path, now: datetime | None = None) -> dict:
    if not os.environ.get("PH_API_KEY"):
        return {"skipped": True, "no_key": "PH_API_KEY"}
    c = cfg["ph"]
    now = now or datetime.now(timezone.utc)
    after = (now - timedelta(hours=c["lookback_hours"])).strftime("%Y-%m-%dT%H:%M:%SZ")
    data = _graphql(QUERY, {"after": after, "topic": c["topic"]})
    edges = ((data.get("posts") or {}).get("edges") or [])
    path = state / "ph_seen.json.gz"
    seen: dict[str, str] = snap.load(path) or {}
    today = now.date().isoformat()
    rows: dict[str, dict] = {}
    for edge in edges:
        node = edge.get("node") or {}
        if node.get("id") in seen or int(node.get("votesCount") or 0) < c["min_votes"]:
            continue
        term = name(node.get("name") or "")
        if not term:
            continue
        seen[node["id"]] = today
        if term in entity.MAKERS and not any(ch.isdigit() for ch in term):
            continue        # "OpenAI" is a company, not this week's new name
        row = rows.setdefault(term, {"term": term, "recent": 0, "votes": 0, "examples": [], "note": "",
                                      "url": node.get("url") or ""})
        row["recent"] += 1
        row["votes"] = max(row["votes"], int(node.get("votesCount") or 0))
        if not row["url"]:
            row["url"] = node.get("url") or ""
        if node.get("tagline"):
            row["examples"].append(node["tagline"])
    for row in rows.values():
        row["note"] = t("note_ph", votes=row["votes"])
    out = sorted(rows.values(), key=lambda r: (-r["votes"], r["term"]))[:c["top"]]
    if edges:       # a failed fetch keeps yesterday's snapshot
        cutoff = (now.date() - timedelta(days=SEEN_DAYS)).isoformat()
        snap.save(path, {k: v for k, v in seen.items() if v >= cutoff})
    return {"read": len(edges), "found": len(out), "capped": len(edges) >= READ_MAX, "terms": out}
