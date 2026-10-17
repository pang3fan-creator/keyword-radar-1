# AGENTS.md

This file is for agents working on `keyword-radar`. Read it before changing behaviour.

## What this project is

`keyword-radar` is a fork of [new-term-radar](https://github.com/zhuyansen/new-term-radar) (MIT). It finds the names of new AI models, products, tools and repositories before they show up in keyword tools, then turns each name into a keyword priority table: the generic search terms behind it, sized and checked for room on page one.

The product is the **discovery and decision layer**, not a site builder.

## Scope (v1)

- Market: overseas; **en-US first**. Domestic (China) is not a target.
- Vertical: **AI models and AI tools only**. Games and entertainment are a later vertical pack; see `docs/06`.
- Output: Markdown + JSON + SQLite. No email, Telegram or cron in v1.
- **Out of scope:** page generation, templates, payments, deployment, notifications.
- Two lanes: fast (named new words, day-level) and slow (combo words, week/month). v1 ships the fast lane first.
- Read `docs/00` (constraints), `docs/05` (methodology) and `docs/06` (scope/backlog) before changing behaviour.

## Repository layout

```
radar/                 runtime code (upstream layout; keep it recognizable)
  __main__.py          CLI entry point; loads .env before a command runs
  env.py               project .env loader (stdlib only)
  sources.py           X and Hugging Face signals
  breakout.py          GitHub breakout signal
  sitemaps.py          new URLs in configured sitemaps
  terms.py             name/term extraction
  judge.py             LLM name judge
  usecases.py          evidence -> generic terms -> keyword table
  competition.py       SERP / KD / DR page-one check
  review.py            14-day Trends review
  store.py             SQLite memory
  report.py            Markdown/JSON reports
  aisa.py, goanyapi.py paid data sources
tests/                 pytest suite; no network, no paid calls
docs/                  analysis and project docs (00-06); make_diagram is upstream
skills/                three Agent Skills from upstream
scripts/               one-off utilities (e.g. migration)
config.json            local config (gitignored)
config.example.json    tracked template
.env                   local keys (gitignored)
.env.example           tracked template
state/                 SQLite and snapshots (gitignored)
report.md / report.json local run output (gitignored)
gitignore/             reference material from the research phase (gitignored)
```

## Setup

```bash
cp config.example.json config.json      # edit: X accounts, sitemaps, topics
cp .env.example .env                    # fill AISA_API_KEY; GOANYAPI_API_KEY optional
```

Python 3.10 or newer. The runtime uses only the standard library. The project venv is `.venv/`; use `.venv/bin/python` when it exists.

## Commands

```bash
.venv/bin/python -m radar daily --out report.md      # fast lane + keyword table + review
.venv/bin/python -m radar sources --out sources.md   # X + HF only
.venv/bin/python -m radar keywords "name" --json     # on-demand keyword table
.venv/bin/python -m radar leads --days 7             # free; inspect stored leads
```

A full `daily` costs about **$0.34** and takes 10–15 minutes with the current 35 X accounts. `keywords` costs about $0.05 per name plus $0.09 per call. State the cost before a paid run, and do not run `daily` twice in a row (the second run reports only the delta).

## Environment and secrets

- `AISA_API_KEY` is required: X posts, Google Trends, search volumes and the models.
- `GOANYAPI_API_KEY` is optional: related queries and one-country Trends series.
- `GITHUB_TOKEN` is optional (raises the GitHub rate limit).
- `TRUSTMRR_API_KEY`, `RESEND_API_KEY`, `EMAIL_FROM`, `RADAR_EMAIL_TO` and `GSC_TOKEN_JSON` are optional and not used in v1.
- `radar/env.py` loads `.env` from the repository root in `main()`. Values in `.env` **override** same-named shell variables. `RADAR_SKIP_ENV_FILE=1` makes tests ignore the developer's real `.env`.
- `aisa.py` reads `AISA_ROUTER_BASE_URL` and `AISA_API_BASE_URL` at import time. They are not in `.env` today. If they join it, move the load earlier or make them call-time.
- Never commit `.env`, `config.json`, `state/` or `report.*`. They are gitignored on purpose. Never print key values.

## Testing

- Write the failing test first for logic changes (TDD). Do not add tests after the code unless it is a regression/reproduction test.
- **Run targeted tests only**, never the full suite: `.venv/bin/python -m pytest tests/test_env.py -q`
- Tests do not make network or paid calls. `tests/conftest.py` disables AISA and GoAnyAPI and sets `RADAR_SKIP_ENV_FILE=1`; keep that isolation.
- One long-running job at a time. Do not run `daily` concurrently with another paid run.

## Coding conventions

- Python 3.10+; standard library only. Do not add a runtime dependency without a clear reason.
- Keep the upstream style and layout. Make surgical changes; do not refactor unrelated code or "improve" adjacent formatting.
- New runtime modules go under `radar/`, one-off scripts under `scripts/`, tests under `tests/`.
- Reports are Markdown + JSON. v1 does not push or email them.

## Current data model direction

The long-term model is `terms` / `term_signals` / `keywords` / `reviews` / `runs`; see `docs/05` §5. Do not drop the existing `leads` table silently: migrate it with `scripts/migrate_leads.py` and keep the old DB. The 2026-10-16 baseline (52 leads) is backed up under `state/backup-2026-10-16/`.

Planned rules from `docs/05`:

- Entity resolution: conservative; merge only contiguous token-subsequence variants from the same source/post/day, and only when the extra token is a maker or a format. Do not merge `pro` / `sol` / `max` variants.
- Selection: after entity resolution, pick keyword-table names by a signal quota, not X-first order. No single signal above 60% of the visible top 20.
- `known_terms`: word-boundary matching, not substring.
- `new`: based on `first_seen`, not a Trends baseline.

## Current status

M0 completed on 2026-10-17:

- 35/35 X accounts, 660 posts; 189 new GitHub repos; 12 sitemaps (toolify fails).
- 5 names read, 8 keyword rows; **no prioritize row** (2 watch, 6 skip).
- Cost: **$0.341**; 75 leads in `state/radar.db`; review pending (14 days).
- Known gaps: `new_sites` (DataForSEO filter), `toolify` sitemap, `gpts` benchmark uncalibrated, X-first selection bias, alias duplicates, some URL-fragment noise.

Next milestone (M1):

1. `scripts/migrate_leads.py`: migrate `leads` into the new tables; reconcile counts.
2. `radar/entity.py`: tail cleanup + conservative alias clustering (tests first).
3. Signal-balanced keyword-table selection (tests first).
4. `known_terms` word-boundary matching; `new` via `first_seen`.

## Git and collaboration

- `origin` is `https://github.com/pang3fan-creator/keyword-radar.git`; the branch is `main`.
- **Never commit or push without the owner's explicit approval.** Approval for one change set does not cover later ones.
- Before a commit: check `git status`, confirm `.env` / `config.json` / `state/` / `report.*` are not staged, and never include secrets.
- The owner speaks Chinese; code, comments, docstrings and this file are in English. Analysis docs may be Chinese; keep them consistent with the file's existing language.

## License and provenance

- This project is MIT, forked from `zhuyansen/new-term-radar`.
- `TrendRadar` (GPL-3.0) is a reference only. Do not copy its code; borrow design ideas at most.
- `Twitter-Trend-Radar` (MIT) is reference material; the `gitignore/` folder is not part of the product.
