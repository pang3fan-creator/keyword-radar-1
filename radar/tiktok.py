"""TikTok's US sound charts: the one source that carries speed.

The chart says how many videos used a sound today and how many more than yesterday
(`usage_change`). That number is the only "is it spreading right now" the radar has, so
it is both a name source and the first gate.

Two charts are read, `popular` and `viral`; the same sound appears on both, so rows are
grouped by `sound_id`. The term is the artist (the short name before "&", "feat." and
friends), and the title only when there is no artist: `Bulin 47` is the name people use,
`Dame Hombro` is the song.

Apify bills every row returned (`apify-default-dataset-item`, about $0.003), so the run
saves what it paid for in `state/tiktok/<day>.json.gz`.
"""
from __future__ import annotations

import gzip
import json
import os
import re
import urllib.request
from datetime import date, datetime
from pathlib import Path

from . import UA

ACTOR = "trendingtiktoksongs/tiktok-trending-sounds-history"
URL = f"https://api.apify.com/v2/acts/{ACTOR}/run-sync-get-dataset-items"
PER_ROW_MICROS = 3000          # billed per dataset item; the account's plan decides the exact price
TIMEOUT = 240
ARTIST_CUT = re.compile(r"\s*(?:&|,|feat\.?|ft\.?)\s+", re.I)


def token() -> str:
    return os.environ.get("APIFY_TOKEN", "").strip()


def _open(req, timeout: int = TIMEOUT):
    """The one network call; tests replace it (tests/conftest.py) like the other sources."""
    return urllib.request.urlopen(req, timeout=timeout)


def artist(raw: str) -> str:
    """'Bulin 47 & Kevin Wai' -> 'bulin 47'; 'Original Sound - foo' -> ''."""
    name = ARTIST_CUT.split(raw or "")[0].split(" - ")[0]
    name = " ".join(name.lower().split()).strip(" -")
    return "" if name.startswith(("original sound", "original audio")) else name


def fetch(cfg: dict, chart: str) -> tuple[list[dict], int]:
    """The chart's rows as Apify returns them, and what they cost."""
    key = token()
    if not key:
        raise RuntimeError("no APIFY_TOKEN")
    c = cfg["tiktok"]
    body = json.dumps({"mode": "latest", "countries": c["countries"], "chartTypes": [chart],
                       "maxRows": c["max_rows"]}).encode()
    req = urllib.request.Request(f"{URL}?token={key}", data=body, method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": UA})
    with _open(req) as res:
        items = json.load(res)
    if not isinstance(items, list):
        raise RuntimeError(f"unexpected Apify answer: {str(items)[:120]}")
    return items, len(items) * PER_ROW_MICROS


def normalize(row: dict, chart: str) -> dict:
    """One chart row as a candidate: the name, the speed, the link."""
    name = artist(row.get("artist") or "")
    title = " ".join(str(row.get("title") or "").lower().split())
    term = name or title
    return {
        "term": term, "source": "tiktok", "first_seen": row.get("observation_date") or date.today().isoformat(),
        "context": f"{row.get('title') or ''} — {row.get('artist') or ''}".strip(" —"),
        "url": row.get("tiktok_url") or "",
        "speed": {"usage_change": int(row.get("usage_change") or 0), "rank": row.get("rank"),
                  "rank_change": row.get("rank_change"), "chart": chart},
        "detail": {"sound_id": row.get("sound_id"), "title": row.get("title"), "artist": row.get("artist"),
                   "usage_count": row.get("usage_count")},
    }


def rising(rows: list[dict], n: int) -> list[dict]:
    """The candidates behind `rows`, one per sound, biggest daily gain first."""
    best: dict[str, dict] = {}
    for row in rows:
        chart = row.get("chart_type") or "popular"
        cand = normalize(row, chart)
        if not cand["term"]:
            continue
        key = str(row.get("sound_id") or cand["term"])
        if key not in best or cand["speed"]["usage_change"] > best[key]["speed"]["usage_change"]:
            best[key] = cand
    return sorted(best.values(), key=lambda r: -r["speed"]["usage_change"])[:n]


def save(state: Path, day: str, rows: list[dict]) -> Path:
    path = state / "tiktok" / f"{day}.json.gz"
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        json.dump({"day": day, "taken_at": datetime.now().isoformat(timespec="seconds"), "rows": rows},
                  fh, ensure_ascii=False)
    return path


def load(state: Path, day: str) -> list[dict] | None:
    path = state / "tiktok" / f"{day}.json.gz"
    if not path.exists():
        return None
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return (json.load(fh) or {}).get("rows") or []
