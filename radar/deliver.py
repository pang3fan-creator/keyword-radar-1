"""The delivery: four sources in, one keyword per line out (docs/Roadmap/07 §5–§7).

The old daily chained eleven extractors into one funnel that ended in a name, a score and a
keyword table built from search volume. This one keeps the four sources that carry what the
owner asked for — a name people already use (X, Product Hunt, Reddit), and the speed of a
format spreading (TikTok) — and turns each surviving candidate into one line:

    term -> long tail -> one keyword -> the page on Google -> four written fields

What is dropped and why is part of the report: a silent filter is a bug, not a feature.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta

from . import aisa, asks, autocomplete, competition, ph, sources, tiktok
from .i18n import t

SOURCES = ("x", "tiktok", "ph", "ask", "seed")

TOOL = re.compile(r"\b(generators?|makers?|editors?|converters?|creators?|removers?|upscalers?|"
                  r"changers?|apps?|tools?|online|free|templates?|how to|videos?|photos?|images?)\b", re.I)
INFO = re.compile(r"\b(lyrics|meaning|net worth|who is|age|height|wife|girlfriend|wiki|bio|"
                  r"dance|challenge|cast|movie|series|story)\b", re.I)
MAX_TAIL_WORDS = 7

SYSTEM = """You write one row of a daily keyword report for one indie developer who ships small English-language sites for overseas users. The reader has no time: every sentence must answer a question he will ask.

Return JSON only, no prose, with exactly these keys:
"usage": what this word is used for right now, in one sentence, in Chinese. Read the evidence; do not guess from the literal meaning.
"page": the single page a developer could build and rank for this keyword, in one sentence, in Chinese. Name the page, not the technology.
"money": who pays for this and how, in one sentence, in Chinese. A concrete buyer and a concrete price or model; if there is no obvious payer, say what the traffic is worth instead.
"timing": why this is worth building now rather than in a month, in one sentence, in Chinese. Use the speed or the date in the evidence; if the evidence does not support "now", say so.

Rules: no buzzwords, no "leverage", no "seamless". If a field would be a guess, write the reason it cannot be known instead of inventing a number."""


def _json(raw: str) -> dict | None:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("\n") + 1:] if "\n" in text else text
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except ValueError:
        return None


def moving(cand: dict, day: date) -> bool:
    """Gate one: it has speed (TikTok), or today is the day it first showed up."""
    speed = cand.get("speed")
    if speed:
        return int(speed.get("usage_change") or 0) > 0
    return cand.get("first_seen") == day.isoformat()


def tail_type(tails: list[str]) -> str:
    if not tails:
        return ""
    tools = sum(1 for s in tails if TOOL.search(s))
    infos = sum(1 for s in tails if INFO.search(s))
    if infos > tools:
        return "info"
    if tools > infos:
        return "tool"
    return "info" if INFO.search(tails[0]) else "tool"


def pick_keyword(tails: list[str], kind: str) -> str:
    """The one tail to check on Google: the right type, short, and the one people type."""
    def score(text: str) -> float:
        own = INFO if kind == "info" else TOOL
        other = TOOL if kind == "info" else INFO
        value = 2.0 if own.search(text) else 0.0
        value -= 1.0 if other.search(text) else 0.0
        value += 1.0 if "ai" in text.split() else 0.0
        return value - 0.2 * len(text.split())

    return max(tails, key=score) if tails else ""


def tails_for(term: str) -> list[str]:
    """How the market finishes this word. Google suggest is free; it answers in ten."""
    got = autocomplete.suggest(term)
    out = []
    for raw in got:
        text = " ".join(str(raw or "").lower().split())
        if not text or text == term or not text.startswith(term):
            continue
        if len(text.split()) > MAX_TAIL_WORDS:
            continue
        out.append(text)
    return out


def window(kinds: dict) -> str:
    """Gate two: how packed the first page already is."""
    tools = int(kinds.get("tool") or 0)
    if tools >= 4:
        return "crowded"
    if tools <= 1:
        return "open"
    return "mixed"


def nine(cand: dict, keyword: str, kind: str, kinds: dict, model: str, chat=aisa.chat) -> dict | None:
    """The four written fields. Missing one drops the line; a half-filled row is worse than none."""
    if not model:
        return None
    user = json.dumps({"term": cand["term"], "context": cand.get("context") or "",
                       "source": cand["source"], "keyword": keyword, "type": kind,
                       "page_one": kinds, "speed": cand.get("speed"), "url": cand.get("url") or ""},
                      ensure_ascii=False)
    data = _json(chat(model, SYSTEM, user, max_tokens=700))
    if not isinstance(data, dict):
        return None
    out = {k: str(data.get(k) or "").strip() for k in ("usage", "page", "money", "timing")}
    return out if all(out.values()) else None


# --- the four sources -------------------------------------------------------------------

def from_x(cfg: dict, state) -> tuple[list[dict], int, list[str]]:
    got = sources.x_new(cfg, state)
    out = []
    for row in got.get("terms") or []:
        posts = row.get("posts") or []
        first = posts[0] if posts else {}
        out.append({"term": row["term"], "source": "x", "first_seen": date.today().isoformat(),
                    "context": first.get("text") or "", "url": first.get("url") or "",
                    "speed": None,
                    "detail": {"accounts": row.get("recent"), "likes": row.get("likes"),
                               "posts": [p.get("url") for p in posts if p.get("url")][:3]}})
    return out, int(got.get("cost_micros") or 0), []


def from_tiktok(cfg: dict, state) -> tuple[list[dict], int, list[str]]:
    rows, cost = [], 0
    for chart in cfg["tiktok"]["charts"]:
        got, spent = tiktok.fetch(cfg, chart)
        rows += [dict(r, chart_type=chart) for r in got]
        cost += spent
    if rows:
        tiktok.save(state, date.today().isoformat(), rows)
    return tiktok.rising(rows, cfg["tiktok"]["top"]), cost, []


def from_ph(cfg: dict, state) -> tuple[list[dict], int, list[str]]:
    got = ph.ph(cfg, state)
    out = []
    for row in got.get("terms") or []:
        out.append({"term": row["term"], "source": "ph", "first_seen": date.today().isoformat(),
                    "context": (row.get("examples") or [""])[0], "url": row.get("url") or "",
                    "speed": None, "detail": {"votes": row.get("votes"), "posts": [row.get("url")]}})
    return out, int(got.get("cost_micros") or 0), []


def from_seed(cfg: dict, state) -> tuple[list[dict], int, list[str]]:
    """Words the owner dropped in by hand: `seeds.txt` in the config directory, one a line."""
    path = cfg["_dir"] / "seeds.txt"
    if not path.exists():
        return [], 0, []
    out = []
    for line in path.read_text().splitlines():
        term = " ".join(line.lower().split())
        if not term or term.startswith("#"):
            continue
        out.append({"term": term, "source": "seed", "first_seen": date.today().isoformat(),
                    "context": "seeds.txt", "url": "", "speed": None, "detail": {}})
    return out, 0, []


def from_ask(cfg: dict, state) -> tuple[list[dict], int, list[str]]:
    conf = cfg["asks"]
    posts, cost, errors = asks.collect(conf)
    kept, failed = asks.classify(conf["model"], posts)
    errors = list(errors) + [f"classify: {e}" for e in failed]
    jobs: dict[str, list[dict]] = {}
    for post in kept:
        jobs.setdefault(post["job"], []).append(post)
    out = []
    for job, group in jobs.items():
        best = max(group, key=lambda p: (p.get("score") or 0, p.get("comments") or 0))
        out.append({"term": job, "source": "ask", "first_seen": date.today().isoformat(),
                    "context": f"{best.get('title') or ''} — {best.get('text') or ''}"[:400],
                    "url": best.get("url") or "", "speed": None,
                    "detail": {"posts": len(group), "subreddits": sorted({p.get("subreddit") or "" for p in group})}})
    return out, int(cost or 0), errors


GATHER = {"x": from_x, "tiktok": from_tiktok, "ph": from_ph, "ask": from_ask, "seed": from_seed}


# --- the run ----------------------------------------------------------------------------

def run(cfg: dict, state, day: date | None = None, skip=(), gather=None,
        serp=None, chat=aisa.chat, seen=None) -> dict:
    """Read four sources, keep what passes both gates, write the rows. Nothing is saved here.

    `seen` holds the terms delivered in the last few days: a word that already had its day is
    dropped with the reason "already" instead of taking one of the ten slots again (07 §7.5).
    """
    day = day or date.today()
    fetched_at = datetime.now().isoformat(timespec="seconds")
    conf = cfg["deliver"]
    get = gather or GATHER
    page = serp or competition.page_one
    result = {"day": day.isoformat(), "rows": [], "dropped": [], "errors": [], "cost_micros": 0,
              "sources": {}}
    cands: dict[str, dict] = {}
    for name in SOURCES:
        if name in skip:
            result["sources"][name] = {"candidates": 0, "skipped": True}
            continue
        try:
            rows, cost, errors = get[name](cfg, state)
        except Exception as exc:  # one dead source must not kill the report
            result["sources"][name] = {"candidates": 0, "error": f"{type(exc).__name__}: {exc}"[:160]}
            result["errors"].append(f"{name}: {type(exc).__name__}: {exc}"[:160])
            continue
        result["cost_micros"] += int(cost or 0)
        result["errors"].extend(errors)
        result["sources"][name] = {"candidates": len(rows)}
        for cand in rows:
            old = cands.get(cand["term"])
            if old is None:
                cands[cand["term"]] = cand
            else:
                # The first source keeps the line (07 §6.1); a later source only lends evidence.
                old.setdefault("also", [])
                if cand["source"] != old["source"] and cand["source"] not in old["also"]:
                    old["also"].append(cand["source"])
                if cand.get("speed") and not old.get("speed"):
                    old["speed"] = cand["speed"]
    seen = {str(term).lower() for term in (seen or ())}
    alive = []
    for cand in cands.values():
        if cand["term"] in seen:
            result["dropped"].append({"term": cand["term"], "reason": "already"})
            continue
        if not moving(cand, day):
            result["dropped"].append({"term": cand["term"], "reason": "moving"})
            continue
        try:
            tails = tails_for(cand["term"])
        except Exception as exc:
            result["errors"].append(f"{cand['term']}: {type(exc).__name__}: {exc}"[:120])
            continue
        if not tails:
            result["dropped"].append({"term": cand["term"], "reason": "tail"})
            continue
        cand["tails"] = tails
        cand["kind"] = tail_type(tails)
        alive.append(cand)
    # Round-robin across the sources, fastest first inside each: the five paid SERP checks must
    # not all go to the one source that happens to carry a speed number.
    pool: dict[str, list[dict]] = {name: [] for name in SOURCES}
    for cand in alive:
        pool[cand["source"]].append(cand)
    for rows in pool.values():
        rows.sort(key=lambda c: -(int((c.get("speed") or {}).get("usage_change") or 0)))
    ordered: list[dict] = []
    while any(pool.values()):
        for name in SOURCES:
            if pool[name]:
                ordered.append(pool[name].pop(0))
    result["dropped"].extend({"term": c["term"], "reason": "cap"} for c in ordered[conf["max_serp"]:])
    per_source: dict[str, int] = {}
    for cand in ordered[:conf["max_serp"]]:
        if per_source.get(cand["source"], 0) >= conf["per_source"]:
            result["dropped"].append({"term": cand["term"], "reason": "cap"})
            continue
        if len(result["rows"]) >= conf["max_items"]:
            result["dropped"].append({"term": cand["term"], "reason": "cap"})
            continue
        keyword = pick_keyword(cand["tails"], cand["kind"])
        try:
            page_one, cost = page(keyword, conf["location_code"])
        except Exception as exc:
            result["errors"].append(f"{keyword}: {type(exc).__name__}: {exc}"[:120])
            continue
        result["cost_micros"] += int(cost or 0)
        kinds: dict[str, int] = {}
        for row in page_one.get("results") or []:
            kind = row.get("kind") or "other"
            kinds[kind] = kinds.get(kind, 0) + 1
        verdict = window(kinds)
        if verdict == "crowded":
            result["dropped"].append({"term": cand["term"], "reason": "crowded"})
            continue
        try:
            fields = nine(cand, keyword, cand["kind"], kinds, conf["model"], chat)
        except Exception as exc:
            result["errors"].append(f"{cand['term']}: {type(exc).__name__}: {exc}"[:120])
            continue
        result["cost_micros"] += int(conf["llm_micros"])
        if not fields:
            result["dropped"].append({"term": cand["term"], "reason": "fields"})
            continue
        per_source[cand["source"]] = per_source.get(cand["source"], 0) + 1
        result["rows"].append({"day": result["day"], "fetched_at": fetched_at, "term": cand["term"], "source": cand["source"],
                               "kind": cand["kind"], "keyword": keyword, **fields,
                               "url": cand.get("url") or "", "context": (cand.get("context") or "")[:400],
                               "evidence": kinds, "window": verdict, "speed": cand.get("speed"), "also": cand.get("also") or [],
                               "detail": cand.get("detail") or {}})
    return result


# --- the report -------------------------------------------------------------------------

def _title(source: str) -> str:
    return t(f"d_src_{source}")


def _why(row: dict) -> str:
    detail = row.get("detail") or {}
    parts = []
    if row.get("speed"):     # the speed can come from a later source, not only from tiktok
        speed = row["speed"]
        parts.append(t("d_why_tiktok", chart=speed.get("chart") or "popular",
                       rank=speed.get("rank") or "?", n=f"{int(speed.get('usage_change') or 0):,}"))
    if row["source"] == "x":
        parts.append(t("d_why_x", n=int(detail.get("accounts") or 0),
                       likes=f"{int(detail.get('likes') or 0):,}"))
    elif row["source"] == "ph":
        parts.append(t("d_why_ph", votes=int(detail.get("votes") or 0)))
    elif row["source"] == "ask":
        parts.append(t("d_why_ask", n=int(detail.get("posts") or 0)))
    return " · ".join(parts)


def markdown(result: dict, before: list[dict] | None = None) -> str:
    rows = result["rows"]
    cost = result["cost_micros"] / 1_000_000
    total = sum(int(s.get("candidates") or 0) for s in result["sources"].values())
    counts = " · ".join(f"{_title(s)} {sum(1 for r in rows if r['source'] == s)}" for s in SOURCES)
    top = max(rows, key=lambda r: int(((r.get("speed") or {}).get("usage_change") or 0))) if rows else None
    out = [f"# {t('d_title', day=result['day'])}", "",
           f"> {t('d_summary', n=len(rows), counts=counts)}"]
    if top:
        why = _why(top) or f"{_title(top['source'])} · {t('d_type_' + top['kind'])}"
        out.append(f"> {t('d_top', term=top['term'], why=why)}")
    out += [f"> {t('d_candidates', candidates=total, n=len(rows))} · {t('d_cost', usd=f'{cost:.3f}')}", ""]
    for source in SOURCES:
        info = result["sources"].get(source) or {}
        out.append(f"## {_title(source)}")
        out.append("")
        mine = [r for r in rows if r["source"] == source]
        if info.get("skipped"):
            out.append(f"*{t('d_skipped')}*")
            out.append("")
            continue
        if info.get("error"):
            out.append(f"- {t('d_error', why=info['error'])}")
        if not mine:
            out.append(f"*{t('d_zero', candidates=int(info.get('candidates') or 0))}*")
            out.append("")
        for row in mine:
            out.append(f"### {row['term']} · {t('d_type_' + row['kind'])}")
            out.append("")
            out.append(f"- **{t('d_keyword')}**: `{row['keyword']}`")
            out.append(f"- **{t('d_usage')}**: {row['usage']}")
            why = _why(row)
            if why:
                out.append(f"- **{t('d_why')}**: {why}")
            link = f" · [原文]({row['url']})" if row.get("url") else ""
            link += f" · {row['fetched_at']}" if row.get("fetched_at") else ""
            out.append(f"- **{t('d_source')}**: {_title(source)}{link}")
            if row.get("also"):
                out.append(f"- **{t('d_also')}**: " + ", ".join(_title(x) for x in row["also"]))
            out.append(f"- **{t('d_page')}**: {row['page']}")
            out.append(f"- **{t('d_money')}**: {row['money']}")
            out.append(f"- **{t('d_timing')}**: {row['timing']}")
            kinds = " · ".join(f"{k} {v}" for k, v in sorted((row.get("evidence") or {}).items()))
            note = "" if row.get("speed") else f" · {t('d_no_speed')}"
            out.append(f"- **{t('d_evidence')}**: {t('d_window', kinds=kinds)} · "
                       f"{t('d_open') if row['window'] == 'open' else t('d_mixed')}{note}")
            out.append("")
    if result["dropped"]:
        out.append(f"## {t('d_dropped')}")
        out.append("")
        bucket: dict[str, list[str]] = {}
        for item in result["dropped"]:
            bucket.setdefault(item["reason"], []).append(item["term"])
        for reason, terms in bucket.items():
            out.append(f"- {t('d_reason_' + reason)}: " + ", ".join(f"`{x}`" for x in terms))
        out.append("")
    if before:
        out.append(f"## {t('d_before')} · {len(before)}")
        out.append("")
        out.append(f"*{t('d_before_note')}*")
        out.append("")
        for item in before:
            out.append(f"- `{item['term']}` · {item['day']} · `{item['keyword']}`")
        out.append("")
    if result["errors"]:
        out.append(f"## {t('d_errors')}")
        out.append("")
        for err in result["errors"]:
            out.append(f"- {err}")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def before(history: list[dict], day: date, days: int = 7) -> list[dict]:
    """Rows already delivered in the last `days` days: shown, not filtered and not re-checked."""
    cut = (day - timedelta(days=days)).isoformat()
    return [r for r in history if cut <= str(r.get("day")) < day.isoformat()]
