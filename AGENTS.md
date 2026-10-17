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
  hn.py                Show HN stories: one lead per name, each story once (free)
  official.py          launch posts on the labs' own feeds, RSS and Atom (free)
  terms.py             name/term extraction
  judge.py             LLM name judge
  entity.py            one term per thing: normalize, merge, canonical
  select.py            signal order and lane; the quota that picks the visible names
  benchmarks.py        the basket that sizes a name, and the checks a benchmark must pass
  leading.py           the plain rule that decides when a name has no size
  usecases.py          evidence -> generic terms -> keyword table
  competition.py       SERP / KD / DR page-one check
  review.py            14-day Trends review
  store.py             SQLite memory: terms / term_signals / reviews (leads is frozen)
  migrate.py           one-off: leads -> terms / term_signals / reviews / runs
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
.venv/bin/python -m radar keywords "name" --json     # on-demand table; prints its cost, records a run
.venv/bin/python -m radar leads --days 7             # free; inspect stored leads
.venv/bin/python scripts/merge_terms.py --dry-run    # one-off: fold twin terms, mark URL echoes
.venv/bin/python scripts/bench_check.py --dry-run    # monthly: check the basket, cache its daily size
.venv/bin/python scripts/new_sites_probe.py           # one paid call ($0.13): what the whois query returns
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
- Selection: after entity resolution, pick keyword-table names by a signal quota, not X-first order. Name slots come from fast-lane terms only; a slow-lane generic phrase earns keyword-table rows but never a name slot. No single signal above 60% of the visible top 20.
- `term_signals`: evidence, score and metadata are per kind. The migration reused the lead's last note for every kind as a one-off; the writer that replaces `store.record()` must not carry that over.
- `known_terms`: word-boundary matching, not substring.
- `new`: based on `first_seen`, not a Trends baseline.

## Current status

M0 completed on 2026-10-17:

- 35/35 X accounts, 660 posts; 189 new GitHub repos; 12 sitemaps (toolify fails).
- 5 names read, 8 keyword rows; **no prioritize row** (2 watch, 6 skip).
- Cost: **$0.341**; 75 leads in `state/radar.db`; review pending (14 days).
- Known gaps at M0 (later closed where noted): `new_sites` (DataForSEO filter; re-checked in M3, the filter works), `toolify` sitemap, `gpts` benchmark uncalibrated, X-first selection bias, alias duplicates, some URL-fragment noise.

M1 completed on 2026-10-17 (`516c6a2..be2d9f7`):

- `radar/entity.py`: one term per thing. 100-pair calibration set (50 merge, 50 do not, 10 pairs taken from the real lead table); an extra token must be a maker, a format, a version or a size, never a variant.
- `radar/select.py`: the visible slots alternate across signals. On the M0 candidates the top 20 went from 20 X to x 6 / hf 6 / breakout 3 / sitemap 5, and the five names read became `deepseek v4.1 flash 1017`, `figcraft`, `gpt 6 astra pro`, `beam 1.0`, `git ai`.
- `known_terms` match whole tokens; a lead is `new` when `first_seen` is today (the keyword table's own `新词?` column still reads the Trends baseline).
- `store.py` reads and writes `terms` / `term_signals` / `reviews`, and `connect()` creates `SCHEMA_NEXT`. `leads` keeps the migrated history and is no longer written.
- Migration: 75 leads became 75 terms, 76 signals and 2 runs; the pre-migration DB is at `state/backup-2026-10-17-pre-migration/`.

M1 debt round, same day (PI review):

- `scripts/merge_terms.py` folded the 7 twin terms the migration left (`mirelo sfx` + `mirelo sfx 2.0`, …) into one row each: aliases, signals and reviews move with the kept row. `record()` now also folds a twin it meets, so no new pair is created.
- A term only a sitemap or a new-site listing found is kept but marked `status='echo'`; `due()` never schedules one and `summary()['pending']` does not count one. 21 rows are echoes, so the 2026-10-31 review budget is not spent on `bitbucket` and friends. The status is computed from every signal the term ever had, so it only moves echo → new: a real signal that found the name keeps it in the review queue even when the next day brings only a sitemap echo.
- `daily` writes a `runs` row: command, ISO start and finish, `cost_micros`, lead and review counts, and the day's errors. The 2026-10-17T20:53 run is in the table (150000 micro-USD, 6m21s); the two migrated rows keep the earlier runs.
- The report's data-status section now says when one signal took the visible slots: a quota that never applied is not a silent success.
- Pre-merge DB: `state/backup-2026-10-17-pre-merge/`.

Still open after M1:

- `reviews` holds no real data before 2026-10-31, when the first 14-day window closes.
- Reading is capped at five names a day and does not rotate: a name ranked 6th or below is only read again when its signal fires again (found in the M0 replay).
- The visible table and the judge still work per surface form; entity resolution runs before storage and before the read, not before the report rows.
- `record()` compares each group against every stored term (`same_entity` is O(terms) per group). Fine at 87 rows, revisit before `terms` reaches a few thousand.

M2 completed on 2026-10-17 (`57ff687`, `01dda93`, `211d602`, `577f30a`, `3a7ec1d`):

- `min_volume` is a label, not a gate: every relevant phrase reaches the table with `volume_status` known / below_threshold / unknown, and `trends_max` now caps paid lookups instead of rows.
- `tests/fixtures/golden_30.json` pins 30 canned words against the thresholds and the decision rules; a day of all watch/skip still passes, because the output count is a reference.
- `radar/benchmarks.py` sizes names against a basket of six, after a quarter-slope, month-over-month and spike check. `scripts/bench_check.py --apply` refreshes the cache monthly; on 2026-10-17 it kept 5 of 6 (`pdf converter` out, month over month +124%) and cost $0.097.
- `radar/leading.py`: when the basket cannot size a name, two or more signals plus a name score of 0.8 or better makes it a priority; the table shows both facts.
- New columns Size and Leading; the benchmark line names what was left out and why; the decision legend says the unknown-size rule.
- `keywords` now feeds the same leading rule from stored signals, prints its cost on stderr and writes a `runs` row, so the manual path is not a second, quieter radar.
- Validation: the 2026-10-17 `daily` read no names (the only candidate scored 0.70), so `keywords "deepseek v4.1 flash 1017"` was run instead and produced a sized row. The daily itself cost $0.099 and wrote its `runs` row.

Still open after M2:

- The benchmark cache is refreshed by hand (`scripts/bench_check.py`); no scheduler in v1.
- `keywords` table in SQLite still has no writer.
- The keyword table's `新词?` column still reads the Trends baseline, not `first_seen`.
- `store.signals_for()` matches the exact canonical only: a name typed as one of its aliases comes back with no signals, so the leading column stays empty for it (fixed in M3).

M3 completed on 2026-10-17 (`669378e`, `f73bef8`):

- `radar/hn.py`: Show HN stories from the last `hn.lookback_hours` (30) with at least `hn.min_points` (30), at most `hn.top` (25) names. The first capitalised run of the title, before the first dash, colon or bracket, is the name; a lone gerund ("Show HN: Building an LLM from Scratch") is not. Each objectID is reported once (`state/hn_seen.json.gz`), and a story that crosses the floor later is still new. Free, no key.
- `radar/official.py`: six launch feeds (OpenAI, Google AI, DeepMind, Hugging Face, Mistral, Microsoft Research). Only posts from the last `official.lookback_days` (7) are read: OpenAI's feed carries 1,299 items back to 2015. A title has to be a name: its first up-to-three words before the first colon, dash, pipe, bracket or comma, with launch words and gerunds dropped, kept when the name carries a digit or the title opens with a launch word. All 12 OpenAI titles in the 2026-10-17 sample were customer stories, essays or research posts and were dropped. One dead feed is a line, not a lost run; a gzipped body is unzipped; Microsoft's feed answers 403 without an `Accept` header.
- Anthropic and Meta AI publish no usable feed (seven Anthropic paths answered 404 on 2026-10-17), so the official source is six feeds, not eight. Product Hunt has no adapter: no `PH_API_KEY` in `.env`, and an unverified adapter is not written.
- `report._source_line()` gives every block without a bespoke line "{n} read, {m} new", the failed feed or query, or the error; a kind with no label still shows, and a skipped sitemap now says so. This is the answer to the M0 `toolify: no URLs read` class of bug: `aisa.call()` drops a failed call from the result, so a source has to count what came back.
- `select.EARLY` starts with `official`, puts `hn` after `breakout`, and keeps the sitemap echo last. `usecases.READ_KINDS` includes both: before this, their names were stored and reviewed but never read for generic terms.
- `store.signals_for()` finds a term by any spelling in its `aliases` (`spark open` -> `muse spark open`); the match is exact membership, so `beam` does not find `beam 1.0`.
- `new_sites` is not broken. `scripts/new_sites_probe.py` (one paid call) got status 20000, 9 sites, $0.131 on 2026-10-17. The M0 gap was inherited from upstream and never reproduced here. The block now returns `read`/`found`/`failed`, and the status line names a query that did not answer.
- Validation: `daily --skip x,hf,breakout,sitemaps,newsites,revenue,asks,gsc,review,judge,usecases,tutorials` against a temporary state dir cost $0 and read 5 HN stories and 28 official posts; it named 10 things (`beam`, `flux.3 image klein`, `granite switch 4.1`, `hiro-acev2`, `timestral`, `muse spark open`, `gemini 4 argon`, `fakeipedia`, `llmspeed`, `stoke money`), and `gemini 4 argon` came from both HN and Google's blog.
- A 40-title sample (20 Show HN, 20 recent official posts) gave 19 names (14 and 5), checked by eye against their titles; the one false positive the sample caught ("building" from "Show HN: Building an LLM from Scratch in TypeScript") is now rejected by the gerund rule. Known misses: a lowercase-start name (`Show HN: rStation`), and names not at the start of a title (`Google Antigravity`, `LFM2.5-24B-A2B`). 14-day hit rates are M5's.
- Cost: $0.131 for the probe; the dry run was free.

Still open after M3:

- Product Hunt: blocked on `PH_API_KEY` / `PH_API_SECRET`; no code until the key exists.
- The five-name reading budget is unchanged; HN and official names compete for the same slots, so a busy launch week can crowd out X.
- `sources` (the frequent job) still runs x/hf only; HN and official run in `daily`.
- Only the six default feeds are verified; adding one is a config edit, not a code change.
- The keyword table's `新词?` column still reads the Trends baseline, not `first_seen` (from M2).
- The benchmark cache is still refreshed by hand; the SQLite `keywords` table still has no writer.

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
