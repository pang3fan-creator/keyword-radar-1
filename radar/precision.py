"""The sitemap/new-site precision sample: ten echo candidates a month, labeled by demand.

An echo term is a name only a sitemap or a new-site listing found: the slug of a page that
already existed (`bitbucket`, `zotero`). It never enters the Trends review, so it has no hit
rate. Its accuracy is sampled instead: one batch of Google Ads monthly searches tells a name
that already had demand (an existing product) from one with none (plausibly new). This is a
proxy, not a human label -- the raw volume and month are stored so the sample can be re-read.

  python -m radar precision --n 10
"""
from __future__ import annotations

import sqlite3
from datetime import date

from . import aisa, store, usecases


def run(cfg: dict, conn: sqlite3.Connection, n: int | None = None, today: date | None = None) -> dict:
    """Sample up to `n` unsampled echoes, one volume batch, one `samples` row per candidate.
    A failed batch writes nothing: the candidates stay unsampled for the next run."""
    today = today or date.today()
    sample_cfg = cfg["review"]["sampling"]
    n = sample_cfg["per_run"] if n is None else n
    candidates = store.echo_candidates(conn, n)
    out: dict = {"sampled": [], "cost_micros": 0, "errors": []}
    if not candidates:
        return out
    try:
        volumes, cost = usecases.volumes([r["term"] for r in candidates], cfg["usecases"]["location_code"])
    except aisa.AisaError as exc:
        return {**out, "errors": [str(exc)[:200]]}
    cut = sample_cfg["existing_volume"]
    for row in candidates:
        got = volumes.get(row["term"]) or {}
        volume = got.get("volume")
        label = "unknown" if volume is None else ("searched" if volume >= cut else "new")
        store.save_sample(conn, row["term_id"], row["source"], today, volume, got.get("month", ""), label)
        out["sampled"].append({**row, "volume": volume, "label": label})
    out["cost_micros"] = cost
    return out
