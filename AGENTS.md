# AGENTS.md

This file is for agents working on `keyword-radar`. Read it before changing behaviour.

## What this project is

`keyword-radar` is a fork of [new-term-radar](https://github.com/zhuyansen/new-term-radar) (MIT). It finds the names of new AI models, products, tools and repositories before they show up in keyword tools, then turns each name into a keyword priority table: the generic search terms behind it, sized and checked for room on page one.

The product is the **discovery and decision layer**, not a site builder.

## Scope (v1)

- Market: overseas; **en-US first**. Domestic (China) is not a target.
- Vertical: **AI models and AI tools only**. Games and entertainment are a later vertical pack; see `docs/Roadmap/06-范围与垂直扩展备忘.md`.
- Output: Markdown + JSON + SQLite. No email, Telegram or cron in v1.
- **Out of scope:** page generation, templates, payments, deployment, notifications.
- Two lanes: fast (named new words, day-level) and slow (combo words, week/month). v1 ships the fast lane first.
- Read `docs/Roadmap/00-项目约束与评估框架.md` (constraints), `docs/Roadmap/05-整合方法论.md` (methodology) and `docs/Roadmap/06-范围与垂直扩展备忘.md` (scope/backlog) before changing behaviour.

## Repository layout

```
radar/                 runtime code (upstream layout; keep it recognizable)
  __main__.py          CLI entry point; loads .env before a command runs
  env.py               project .env loader (stdlib only)
  sources.py           X and Hugging Face signals
  breakout.py          GitHub breakout signal
  sitemaps.py          new URLs in configured sitemaps
  hn.py                Show HN stories: one lead per name, each story once (free)
  official.py          launch posts on the labs' own feeds, RSS and Atom (free)
  ph.py                Product Hunt launches ranked by votes (free, needs PH_API_KEY)
  autocomplete.py      Google suggest, free: the slow lane's discovery
  slow.py              the weekly combo-word list, on the fast lane's own chain
  precision.py         the sitemap/new-site name precision sample (one volume batch)
  terms.py             name/term extraction
  judge.py             LLM name judge
  entity.py            one term per thing: normalize, merge, canonical
  select.py            signal order and lane; the quota that picks the visible names
  benchmarks.py        the basket that sizes a name, and the checks a benchmark must pass
  leading.py           the plain rule that decides when a name has no size
  usecases.py          evidence -> generic terms -> keyword table
  competition.py       SERP / KD / DR page-one check
  review.py            multi-window review: 1d/3d free, 7d/14d, slow 14d/30d
  store.py             SQLite memory: terms / term_signals / reviews / samples (leads is frozen)
  migrate.py           one-off: leads -> terms / term_signals / reviews / runs
  report.py            Markdown/JSON reports
  aisa.py, goanyapi.py paid data sources
tests/                 pytest suite; no network, no paid calls
docs/                  docs index; Roadmap/ (00-06: constraints, research, methodology, scope); 里程碑.md
docs/make_diagram/     the flow diagram script and GIFs (upstream)
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
.venv/bin/python -m radar keywords "name" --json     # on-demand table; prints its cost, records a run
.venv/bin/python -m radar leads --days 7             # free; inspect stored leads
.venv/bin/python scripts/merge_terms.py --dry-run    # one-off: fold twin terms, mark URL echoes
.venv/bin/python scripts/bench_check.py --dry-run    # monthly: check the basket, cache its daily size
.venv/bin/python scripts/new_sites_probe.py           # one paid call ($0.13): what the whois query returns
.venv/bin/python -m radar slow --out slow.md         # weekly: combo words; --free skips every paid step
.venv/bin/python -m radar precision --n 10           # monthly: sitemap/new-site name precision sample (~$0.09)
```

A full `daily` costs about **$0.34–0.40** (2026-10-18: $0.395) and takes 10–15 minutes with the current 35 X accounts. `keywords` costs about $0.05 per name plus $0.09 per call. State the cost before a paid run, and do not run `daily` twice in a row (the second run reports only the delta).

## Environment and secrets

- `AISA_API_KEY` is required: X posts, Google Trends, search volumes and the models.
- `GOANYAPI_API_KEY` is optional: related queries and one-country Trends series.
- `GITHUB_TOKEN` is optional (raises the GitHub rate limit).
- `PH_API_KEY` is optional: the Product Hunt signal (⑩). A developer token from the Product Hunt dashboard; public read, no client secret.
- `TRUSTMRR_API_KEY` is optional: the weekly revenue signal (⑥).
- `GSC_TOKEN_JSON` and the `gsc` config are optional: the Search Console signal (④).
- `RESEND_API_KEY`, `EMAIL_FROM` and `RADAR_EMAIL_TO` are optional and only used by `--mail`; v1 does not send.
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

The long-term model is `terms` / `term_signals` / `keywords` / `reviews` / `runs`; see `docs/Roadmap/05-整合方法论.md` §5. Do not drop the existing `leads` table silently: migrate it with `scripts/migrate_leads.py` and keep the old DB. The 2026-10-16 baseline (52 leads) is backed up under `state/backup-2026-10-16/`.

Planned rules from `docs/Roadmap/05-整合方法论.md`:

- Entity resolution: conservative; merge only contiguous token-subsequence variants from the same source/post/day, and only when the extra token is a maker or a format. Do not merge `pro` / `sol` / `max` variants.
- Selection: after entity resolution, pick keyword-table names by a signal quota, not X-first order. Name slots come from fast-lane terms only; a slow-lane generic phrase earns keyword-table rows but never a name slot. No single signal above 60% of the visible top 20.
- `term_signals`: evidence, score and metadata are per kind. The migration reused the lead's last note for every kind as a one-off; the writer that replaces `store.record()` must not carry that over.
- `known_terms`: word-boundary matching, not substring.
- `new`: based on `first_seen`, not a Trends baseline.

## Current status

Last completed milestone: **M5 (2026-10-18)**. The record of each milestone -- numbers, commits, what it changed, what it left open -- is in `docs/里程碑.md`; read the latest section before you trust a count.

Snapshot (2026-10-18, re-read from `state/radar.db`):

- 108 terms (84 fast, 24 slow); 57 reviews (44 at 1d, 13 at 3d; no paid window yet).
- `runs` #5 `daily`: $0.395, 20 leads stored, no errors; #6 `precision`: $0.090, 10 sampled (7 new / 3 searched / 0 unknown).
- First paid rows: fast 7d/14d on **2026-10-29**; slow 14d/30d on **2026-11-14**.
- The daily run is manual: the owner says when to run it. There is no scheduler in the runtime.

Still open after M5 (the full list is in `docs/里程碑.md`):

- `name_real` is the judge's strong bar, not a human label, and `precision` is a volume threshold, not "is this an existing product". A human spot check (50 names) is still open.
- The review is a sample: `per_day` 5 per lane against about 20 new leads a day, so `due` will grow; the report prints waiting and due per lane.
- The 7d/14d rows arrive with the final check by design; a term that never reaches 14 days is never checked.
- The 24 slow words are mostly the migrated generic phrases; their 30d outcome measures the keyword-table reflux, not M4's combo words.
- The slow 30d series is 61 days; whether the endpoint returns that span is unproven until 2026-11-14.
- No scheduler; Trends Rising as discovery; `sources` does not run hn/official/ph/slow; no MCP tools for slow/precision; the benchmark refresh is by hand; the SQLite `keywords` table has no writer; the keyword table's `新词?` column still reads the Trends baseline.
- PI review follow-up: `_free` has no cap, so at a few hundred new terms a day the 1d/3d rows grow by hundreds a day (free, but the table grows). Revisit with a cap only when it actually grows.
- PI review follow-up: `name_real` reads the stored score at check time, so a 1d row answers "does it still stand at the check", not "was it a name on day one". Nail the definition down with the 50-name human spot check (M6).

## Before you hand work over

Three review rounds found the same class of miss: the handover said "done" and the repository said otherwise. Run this list first, and answer each line in the handover message.

- Numbers: every count you quote (terms, signals, pending, runs, cost, test counts) is re-read from the database or the command output, never remembered.
- Silence: a constraint that did not hold says so in the report or the data-status section. A dead quota, a skipped source, a failed benchmark or a downgraded term that passes without a line is a bug.
- Half-done: an item marked done traces to a line of code. If only the storage half or the read half landed, write "partial, Mx".
- Orphans: no table that nobody writes or nobody reads, no function added without a caller, no promise in these docs without a check.

## Git and collaboration

- `origin` is `https://github.com/pang3fan-creator/keyword-radar.git`; the branch is `main`.
- **Never commit or push without the owner's explicit approval.** Approval for one change set does not cover later ones.
- Before a commit: check `git status`, confirm `.env` / `config.json` / `state/` / `report.*` are not staged, and never include secrets.
- The owner speaks Chinese; code, comments, docstrings and this file are in English. Analysis docs may be Chinese; keep them consistent with the file's existing language.

## License and provenance

- This project is MIT, forked from `zhuyansen/new-term-radar`.
- `TrendRadar` (GPL-3.0) is a reference only. Do not copy its code; borrow design ideas at most.
- `Twitter-Trend-Radar` (MIT) is reference material; the `gitignore/` folder is not part of the product.
