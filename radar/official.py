"""Signal ⑧: the official blog, where a model is named before anyone writes about it.

A launch post is the earliest public name for a model or a tool: "Gemini 4 Argon: Built to
solve your hardest problems". The same feed also carries customer stories ("How Itau is
building generative AI for its customers") and think-pieces, which name products that are
already old; those titles are sentences, not a name followed by a colon.

So a title has to be a name: its first words, up to three, before the first colon, dash,
pipe, bracket or comma. Leading launch words ("Introducing", "Welcome") and gerunds
("Developing Gemini 4 Argon") are dropped first. The name is kept only when it carries a
digit or a version, or when the title opens with a launch word -- "Introducing Fable" is a
launch, "Benefit Street Partners answers questions" is not. A listicle ("5 ways to ...")
is rejected: its first word is a number, not a name.

Feeds are a config list (official.feeds, name -> URL). RSS and Atom both parse; a gzipped
body regardless of the request is unzipped. Only posts from the last `lookback_days` are
read, because a feed carries its whole archive (OpenAI's had 1,299 items). Each link is
reported once (state/official_seen.json.gz). A dead feed -- a timeout, a 404, or a
page that is not a feed -- is a line, not a lost run.
"""
from __future__ import annotations

import gzip
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from . import UA, entity, snap
from .i18n import t

# The first word decides whether a digit-less name is a launch ("Introducing Fable").
OPENS_WITH_LAUNCH = re.compile(r"^(introduc|announc|launch|unveil|releas|welcome)", re.I)
DROP = {"the", "a", "an", "our", "new", "this", "that"}
SEP = re.compile(r"\s*[:\u2013\u2014|(,]\s*")
START = re.compile(r"^[A-Z0-9]")
NUMERIC = re.compile(r"^\d+\+?$")
GENERIC = {"the", "a", "an", "our", "new", "pricing", "price", "plan", "plans", "update", "updates",
           "feature", "features", "model", "models", "tool", "tools", "app", "apps", "api", "version",
           "beta", "docs", "documentation", "platform", "release", "notes", "more", "it", "this", "that"}
SEEN_DAYS = 60


def _clean(word: str) -> str:
    return word.strip(",.:;!?\"'\u2122\u00ae")


def launch_name(title: str) -> str | None:
    """'Gemini 4 Argon: Built to solve your hardest problems' -> 'gemini 4 argon';
    'Introducing Fable' -> 'fable'; a customer story or a listicle -> None."""
    text = title.strip()
    words = [w for w in SEP.split(text, maxsplit=1)[0].split() if _clean(w)]
    while words:
        word = _clean(words[0])
        if OPENS_WITH_LAUNCH.match(word) or word.lower() in DROP or \
                (len(word) >= 6 and word.lower().endswith("ing") and len(words) > 1):
            words.pop(0)
            continue
        break
    run: list[str] = []
    for word in words:
        token = _clean(word)
        if not (START.match(token) or any(ch.isdigit() for ch in token)):
            break        # "o3" starts lowercase, but a digit makes it a name word
        run.append(token)
        if len(run) == 3:
            break
    if not run:
        return None
    name = " ".join(run).lower()
    if NUMERIC.fullmatch(run[0]) or len(name) < 3 or all(w in GENERIC for w in name.split()):
        return None
    if name in entity.MAKERS and not any(ch.isdigit() for ch in name):
        return None     # "OpenAI" is a company, not this week's new name
    if any(ch.isdigit() for ch in name) or OPENS_WITH_LAUNCH.match(_clean(title.split()[0])):
        return name
    return None


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _when(text: str) -> datetime | None:
    try:
        got = parsedate_to_datetime(text.strip())
    except (TypeError, ValueError):
        try:
            got = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    return got if got.tzinfo else got.replace(tzinfo=timezone.utc)


def items(body: bytes) -> list[dict]:
    """The (title, link, published) of every RSS item or Atom entry, in feed order."""
    out = []
    for el in ET.fromstring(body).iter():
        if _local(el.tag) not in ("item", "entry"):
            continue
        title, link, published = "", "", None
        for child in el:
            tag = _local(child.tag)
            if tag == "title" and not title:
                title = "".join(child.itertext()).strip()
            elif tag == "link" and not link:
                link = (child.get("href") or "".join(child.itertext())).strip()
            elif tag in ("pubdate", "published", "updated") and published is None and child.text:
                published = _when(child.text)
        if title:
            out.append({"title": title, "link": link, "published": published})
    return out


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.8"})
    with urllib.request.urlopen(req, timeout=30) as res:
        body = res.read()
    return gzip.decompress(body) if body[:2] == b"\x1f\x8b" else body


def official(cfg: dict, state: Path, now: datetime | None = None) -> dict:
    c = cfg["official"]
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=c["lookback_days"])
    today = now.date().isoformat()
    path = state / "official_seen.json.gz"
    seen: dict[str, str] = snap.load(path) or {}
    rows: dict[str, dict] = {}
    read, failed = 0, []
    for name, url in c["feeds"].items():
        try:
            body = _get(url)
            parsed = items(body)    # a web page is not a feed; it must not cost the others
        except Exception:  # noqa: BLE001
            failed.append(name)
            continue
        for item in parsed:
            if not item["published"] or item["published"] < since:
                continue        # the feed's archive is not today's news
            read += 1
            key = item["link"] or item["title"]
            if key in seen:
                continue
            seen[key] = today
            term = launch_name(item["title"])
            if not term:
                continue
            row = rows.setdefault(term, {"term": term, "recent": 0, "examples": [],
                                         "note": t("note_official", feed=name)})
            row["recent"] += 1
            row["examples"].append(item["title"])
    out = sorted(rows.values(), key=lambda r: r["term"])[:c["max_per_run"]]
    if read:        # a failed fetch keeps yesterday's snapshot
        cutoff = (date.fromisoformat(today) - timedelta(days=SEEN_DAYS)).isoformat()
        snap.save(path, {k: v for k, v in seen.items() if v >= cutoff})
    return {"read": read, "found": len(out), "feeds": len(c["feeds"]), "failed": failed, "terms": out}
