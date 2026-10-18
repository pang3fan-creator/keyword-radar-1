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
.venv/bin/python -m radar slow --out slow.md         # weekly: combo words; --free skips every paid step
.venv/bin/python -m radar precision --n 10           # monthly: sitemap/new-site name precision sample (~$0.09)
```

A full `daily` costs about **$0.34** (up to $0.38 once the paid review windows are due) and takes 10–15 minutes with the current 35 X accounts. `keywords` costs about $0.05 per name plus $0.09 per call. State the cost before a paid run, and do not run `daily` twice in a row (the second run reports only the delta).

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
- Anthropic and Meta AI publish no usable feed (seven Anthropic paths answered 404 on 2026-10-17), so the official source is six feeds, not eight.
- `radar/ph.py`: Product Hunt launches in the AI topic, last `ph.lookback_hours` (26), ordered by votes, `ph.min_votes` (50) to count. `PH_API_KEY` is the dashboard's developer token (public read; no client secret needed). A product is reported once (`state/ph_seen.json.gz`); a launch below the floor is not marked seen, so one that climbs later is still new. `Notion: Context for your agents` is read as `notion context`: the brand alone is the old name.
- `report._source_line()` gives every block without a bespoke line "{n} read, {m} new", the failed feed or query, or the error; a kind with no label still shows, and a skipped sitemap now says so. This is the answer to the M0 `toolify: no URLs read` class of bug: `aisa.call()` drops a failed call from the result, so a source has to count what came back.
- `select.EARLY` starts with `official`, puts `hn` after `breakout`, and keeps the sitemap echo last. `usecases.READ_KINDS` includes both: before this, their names were stored and reviewed but never read for generic terms.
- `store.signals_for()` finds a term by any spelling in its `aliases` (`spark open` -> `muse spark open`); the match is exact membership, so `beam` does not find `beam 1.0`.
- `new_sites` is not broken. `scripts/new_sites_probe.py` (one paid call) got status 20000, 9 sites, $0.131 on 2026-10-17. The M0 gap was inherited from upstream and never reproduced here. The block now returns `read`/`found`/`failed`, and the status line names a query that did not answer.
- Validation: `daily --skip x,hf,breakout,sitemaps,newsites,revenue,asks,gsc,review,judge,usecases,tutorials` against a temporary state dir cost $0 and read 5 HN stories and 28 official posts; it named 10 things (`beam`, `flux.3 image klein`, `granite switch 4.1`, `hiro-acev2`, `timestral`, `muse spark open`, `gemini 4 argon`, `fakeipedia`, `llmspeed`, `stoke money`), and `gemini 4 argon` came from both HN and Google's blog.
- A 40-title sample (20 Show HN, 20 recent official posts) gave 19 names (14 and 5), checked by eye against their titles; the one false positive the sample caught ("building" from "Show HN: Building an LLM from Scratch in TypeScript") is now rejected by the gerund rule. Known misses: a lowercase-start name (`Show HN: rStation`), and names not at the start of a title (`Google Antigravity`, `LFM2.5-24B-A2B`). 14-day hit rates are M5's.
- Cost: $0.131 for the probe; the dry run was free.

M3 review round, same day (PI review) (`dcde0bb`):

- Blocker: a feed that answered with a web page (a challenge page, a 404 body) threw in `items()` outside the try, and the whole official block became one error -- the docstring claimed the opposite. Parsing is inside the try now; a test feeds a good RSS and an HTML page and asserts `found == 1`, `failed == ["b"]`.
- A maker alone read as a new name: "Show HN: OpenAI released GPT-6" -> `openai`, "OpenAI: our new model" -> `openai`. `entity.MAKERS` rejects a name that is a known maker with no digit or version in it, in HN, official and PH; `openai o3` keeps its place.
- A full Algolia page (100) or Product Hunt page (50) dropped its tail in silence; both blocks carry `capped`, and the status line says "hit the page cap".
- `signals_for()` escapes `%` and `_` in the alias pattern (`ESCAPE '\'`). The membership check already kept the answer right; this stops the query from over-fetching.
- `tests/fixtures/titles_40.json` pins the 40-title sample: 19 names and 2 known misses (a lowercase first letter, a name that is not at the start of the title). Fixing a miss means updating the fixture.
- The `st_ran` branch has a test now.
- Free run with all three: 5 HN + 28 official + 20 PH posts read, 20 names in the table, $0.

Still open after M3:

- Product Hunt's `PH_API_KEY` is a developer token; if it is revoked the status line shows the HTTP error, not a quiet zero.
- The five-name reading budget is unchanged; HN and official names compete for the same slots, so a busy launch week can crowd out X.
- `sources` (the frequent job) still runs x/hf only; HN, official and PH run in `daily`.
- Only the six default feeds are verified; adding one is a config edit, not a code change. The 40-title fixture is one day's sample: a new feed or a fixed miss needs the fixture updated.
- The keyword table's `新词?` column still reads the Trends baseline, not `first_seen` (from M2).
- The benchmark cache is still refreshed by hand; the SQLite `keywords` table still has no writer.
- `ph.name()` reads only the subtitle's first word, and `SUB` (the/for/with/...) drops it when it is a function word: "Notion: for your agents" would come back as `notion` alone (fixed in M5: `BLOCK` skips filler words and pairs the brand with the first content word, `notion agents`).
- PH name extraction has no negative fixture variants (a "by <maker>" suffix, a two-colon title); the 40-title fixture covers HN and the official feeds only (fixed in M5: `tests/test_ph.py` pins those variants).

M4 completed on 2026-10-17 (`058479a`, `70c5c47`):

- `radar/autocomplete.py`: seeds = `slow.objects` (20) x `slow.actions` (8); any list fits. One free request per seed to Google's suggest endpoint. A candidate must carry the seed's category word (a plural counts), have 2-6 words, not open with a question word, and not be a `known_terms` entry. A failed seed is a line; a malformed answer is an error, not an empty list. The first run read 160 seeds into 855 candidates.
- `radar/slow.py`: deals the volume cap across categories (`spread`), then walks the fast lane's own chain -- `usecases.volumes`, `solo_series`, `measure`, `competition.assess` -- and balances the table (<=8 per category, <=3 near-copies).
- The weekly run is its own command and report (`slow.md` + `slow.json`); `daily` never calls it. Slow rows are `terms.window='slow'`, which finally reads the column M1 created: no visible name slot (`select.SLOW`), no five-name read (`READ_KINDS`), no 14-day review (`due()` and `summary()` exclude them). A slow word a fast signal later names flips to `window='fast'` and becomes reviewable.
- First real run: 160 seeds, 855 candidates, 30 rows, **$0.349**, 7m20s, no paid errors; the strongest row was `ai tattoo generator` (14,800/mo, rising, KD 26, 329 pages). The volume batch has a base charge and grows with the word count (M5 measured $0.09 for ten words; 250 words printed about $0.24), so the caps are now 120 volumes / 25 shapes / 5 page-one, and the report prints volumes / Trends / page-one spend separately so the next run proves the estimate.
- Only the visible rows (<=30) are stored, not the 855 candidates; the JSON keeps the run.
- Tests: autocomplete parse/filter/cap/failure, the shared chain and the store write, the category deal, the review exclusion and the fast-signal promotion, the report's failure, caps and spend lines.

Still open after M4:

- Trends Rising as a **discovery** channel: M4 uses Trends only for the shape.
- The weekly run is manual; no scheduler in v1, and `sources` does not run the slow lane.
- The seed list is 20 x 8; the 115 roots and 63 seeds are not in the repository, so a different list is a config edit.
- The tuned weekly cost (~$0.19) is an estimate until the next paid run prints its split.

M5 completed on 2026-10-18 (`67a57e1`):

- `radar/review.py`: windows come from `review.windows` (fast 1/3/7/14, slow 14/30). 1d/3d are local and free: `name_real` is the judge's strong bar (`review.name_real_score`, 0.80) and `persistence` is `last_seen > first_seen`; the row keeps `age_days`, so a window read late says so in the report. 7d/14d (and slow 14d/30d) are one Trends series per lane read at the final check, each horizon cut at `first_seen + days`: a late 7d row still says what happened in the first week, and two windows never pay twice.
- `save_review()` replaces `save_verdict()`: one row per term and window, `name_real` / `persistence` / `search_rise` separate, the old mixed verdict only inside `metrics`. The 14d/30d rows are `final` and move the term to `watching`.
- A failed Trends batch is an error line for that lane (the other lane still runs) and the terms stay due; a term missing one variant answer stays due too. Both reach `runs.errors` and the report's ⑤ section.
- `radar/precision.py` + `radar precision --n 10`: samples unsampled `status='echo'` terms, one Google Ads batch, labels `new` / `searched` (>= `review.sampling.existing_volume`, 1000/mo) / `unknown`, writes `samples`; the report and `leads` aggregate the last 90 days.
- `merge_terms()` carries `window` (fast if either side is fast). `ph.name()` pairs a one-word brand with the first non-filler word after the colon ("Notion: for your agents" -> `notion agents`); tests pin the `by <maker>` suffix, a two-colon title, articles and launch verbs.
- Validation (2026-10-18): daily **$0.395** (`runs` #5, 09:59:28, no errors), 20 leads stored, the review part $0 (no paid window due): **44 rows at 1d, 13 at 3d**; 30 of the 1d names passed the strong bar, 14 did not. Terms after the run: 108 (84 fast, 24 slow). `radar precision --n 10` cost **$0.090** (`runs` #6) and labeled 7 new / 3 already searched (aws 368k, bitbucket 33.1k, engram 12.1k), 0 unknown.
- First paid rows: fast 7d/14d on **2026-10-29** (the 10-15 terms reach 14 days), slow 14d/30d on **2026-11-14**. Until then the report says "nothing in Trends (the first check is due ...)".
- Cost correction: the precision run cost $0.090, not the ~$0.01 in the plan: the volume lookup has a fixed base charge. The M4 note above is corrected the same way.

Still open after M5:

- `name_real` is the judge's strong bar, not a human label, and `precision` is a volume threshold, not "is this an existing product". A human spot check (50 names) is still open.
- The review is a sample: `per_day` 5 per lane against about 20 new names a day, so `due` will grow; the report prints waiting and due per lane.
- The 7d/14d rows arrive with the final check by design (there is no early 7d request), and a term that never reaches 14 days is never checked.
- The 24 slow words are mostly the migrated generic phrases; their 30d outcome measures the keyword-table reflux, not M4's combo words.
- The slow 30d series is 61 days; whether the endpoint returns that span is unproven until 2026-11-14.
- Trends Rising as discovery, a scheduler, `sources` for hn/official/ph/slow, MCP tools for slow/precision, the hand-run benchmark refresh, the `keywords` table writer and the `新词?` column are unchanged from earlier sections.

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
