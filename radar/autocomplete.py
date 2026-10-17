"""The slow lane's free discovery: what Google suggests for a seed phrase.

`slow.objects` x `slow.actions` make seeds ("ai headshot generator"); each seed is one
request to Google's public suggest endpoint (no key, ten suggestions). A suggestion is a
candidate only when it shares a word with its seed, has two to six words, does not open
with a question word, and is not a known term -- otherwise it is not a combo word, it is
"how to ..." or a brand the radar already covers.

The endpoint is unofficial. A seed that fails is a line in the errors, never an empty
answer that looks like "Google suggests nothing".
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request

from . import UA, entity

URL = "https://suggestqueries.google.com/complete/search"
LEAD_STOP = {"how", "what", "why", "when", "where", "who", "is", "are", "can", "does", "do", "should", "will"}


def _get(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as res:
        return json.loads(res.read().decode("utf-8", "replace"))


def suggest(seed: str) -> list[str]:
    """Google's ten suggestions for the seed, in its order."""
    query = urllib.parse.urlencode({"client": "firefox", "hl": "en", "gl": "us", "q": seed})
    body = _get(f"{URL}?{query}")
    if not isinstance(body, list) or len(body) < 2 or not isinstance(body[1], list):
        raise RuntimeError(f"unexpected autocomplete answer: {str(body)[:80]}")
    return [str(s) for s in body[1]]


def seeds(cfg: dict) -> list[str]:
    c = cfg["slow"]
    return [" ".join(c["template"].format(object=obj, action=act).lower().split())
            for obj in c["objects"] for act in c["actions"]]


def _matches_object(term: str, obj: str) -> bool:
    """A combo belongs to a category only if the category's word is in it: "ai picture
    summarizer" is not a headshot term because it shares an action word with one.
    A plural still counts ("ai headshots free" has the headshot category)."""
    if not obj:
        return True
    keys = entity.tokens(obj)
    words = entity.tokens(term)
    if len(keys) == 1:
        return any(w.startswith(keys[0]) for w in words)
    return any(words[i:i + len(keys)] == keys for i in range(len(words) - len(keys) + 1))


def _objects(term: str, cfg: dict) -> list[str]:
    """The configured objects whose words appear in the candidate (the category it belongs to)."""
    words = entity.tokens(term)
    out = []
    for obj in cfg["slow"]["objects"]:
        keys = entity.tokens(obj)
        if keys and any(words[i:i + len(keys)] == keys for i in range(len(words) - len(keys) + 1)):
            out.append(obj)
    return out


def candidates(seeds: list[str], known, cfg: dict) -> tuple[list[dict], list[str]]:
    """(candidates, errors). `known(term)` is config.known: a phrase it covers is not new."""
    c = cfg["slow"]
    out: dict[str, dict] = {}
    errors: list[str] = []
    for seed in seeds[:c["max_queries"]]:
        try:
            suggestions = suggest(seed)
        except Exception as exc:  # noqa: BLE001  one blocked seed is a line, not a lost run
            errors.append(f"{seed}: {exc}")
            continue
        time.sleep(c["delay"])
        category = (_objects(seed, cfg) or [""])[0]
        for raw in suggestions:
            term = entity.normalize(raw)
            words = term.split()
            if term == seed or not 2 <= len(words) <= 6 or words[0] in LEAD_STOP:
                continue
            if not _matches_object(term, category) or known(term):
                continue
            row = out.setdefault(term, {"term": term, "objects": [], "seeds": []})
            row["seeds"].append(seed)
            for obj in _objects(term, cfg) or [category]:
                if obj and obj not in row["objects"]:
                    row["objects"].append(obj)
    return list(out.values()), errors
