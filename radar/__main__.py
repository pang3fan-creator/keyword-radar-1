"""new-term-radar: new words people already use, before the keyword tools see them.

  python -m radar daily    [--config config.json] [--state state] [--out report.md] [--skip x,tiktok,ph,asks] [--mail]

`daily` reads four sources and writes one keyword per line (docs/Roadmap/07):
  x        what the seven accounts say is spreading (AIsa; about $0.02 a run)
  tiktok   the US sound charts: the name, and how many videos it gained today (Apify)
  ph       Product Hunt launches in the AI topic, with their taglines (PH_API_KEY)
  ask      Reddit posts asking for a tool, rewritten into one job phrase (AIsa)

Each surviving word gets its long tail from Google suggest, one keyword, the first page of
Google (DataForSEO, about $0.002 a keyword), and four written fields from a small model. A word
that fails a gate is listed with the reason; a source that fails says so. The report lands
in `reports/<date>.md` and the rows in the `deliveries` table, so a later question is a
query, not a re-run.

  python -m radar keywords "name" [--repo "name=owner/repo"] [--json]   the old keyword table
  python -m radar deliveries [--days 7] [--json]                        what the new lane shipped
  python -m radar leads    [--days 7] [--json]                          what the old radar kept
  python -m radar pains    "keyword" [--json]                           complaints about a kind of tool
  python -m radar mcp                                                   the MCP server on stdio

The old signals (hf, breakout, sitemaps, new sites, revenue, hn, official, gsc, review,
usecases, slow, precision) are no longer wired into `daily`; their modules stay until the
new lane has run for three days (07 §9 Q5).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from . import (config, deliver, env, notify, pains, precision, report, review, slow, sources, store,
               usecases)
from .i18n import t

SKIPPABLE = {"x", "tiktok", "ph", "asks"}


def run(fn, skip: bool = False) -> dict:
    """One signal failing still leaves a report: its error takes its place."""
    if skip:
        return {"skipped": True}
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {' '.join(str(exc).split())[:160]}"}


def _finish(args, text: str, subject: str) -> None:
    if args.out:
        Path(args.out).write_text(text)
    print(text)
    if args.mail:
        print(notify.send(subject, text))


def cmd_sources(args, cfg: dict, state: Path) -> int:
    blocks = {"x": run(lambda: sources.x_new(cfg, state), "x" in args.skip),
              "hf": run(lambda: sources.hf_new(cfg, state), "hf" in args.skip)}
    lead, judged = report.leads(cfg, blocks)
    conn = store.connect(state)
    extra = {"judge": judged, "record": run(lambda: {"recorded": store.record(conn, report.to_record(cfg, lead))})}
    errors = any(b.get("error") for b in (*blocks.values(), *extra.values()))
    if report.named(cfg, lead) or errors:
        _finish(args, report.sources(cfg, lead, blocks, extra), f"New-term radar · sources {date.today()}")
    else:
        print(t("sources_quiet") + "; ".join(f"{k} {v.get('posts', v.get('models', t('dash')))}" for k, v in blocks.items()))
    return 0


BACKUP_DAYS = 30


def backup(state: Path, day: date) -> None:
    """A daily copy of the only source of truth (07 §7.6); the last 30 days are kept."""
    target = state / "backup"
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(state / "radar.db", target / f"{day.isoformat()}.db")
    cut = (day - timedelta(days=BACKUP_DAYS)).isoformat()
    for old in target.glob("*.db"):
        if old.stem < cut:
            old.unlink(missing_ok=True)


def cmd_daily(args, cfg: dict, state: Path) -> int:
    """Four sources, two gates, one keyword a line: the delivery (07 §5-§7)."""
    started = datetime.now().isoformat(timespec="seconds")
    day = date.today()
    skip = {"ask" if name == "asks" else name for name in args.skip}
    conn = store.connect(state)
    days = int(cfg["deliver"].get("dedupe_days") or 0)
    recent = store.deliveries(conn, days or 7, day, include_today=True)
    history = [row for row in recent if str(row["day"]) < day.isoformat()]   # the "before" list
    seen = {row["term"] for row in recent} if days else set()                # today included: a rerun repeats nothing
    result = deliver.run(cfg, state, day, skip=skip, seen=seen)
    text = deliver.markdown(result, history)
    reports = cfg["_dir"] / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / f"{day.isoformat()}.md").write_text(text)
    (reports / f"{day.isoformat()}.json").write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str))
    run_id = store.record_run(
        conn, "daily", started, datetime.now().isoformat(timespec="seconds"), result["cost_micros"],
        {"delivered": len(result["rows"]),
         "candidates": sum(int(s.get("candidates") or 0) for s in result["sources"].values())},
        result["errors"])
    store.save_deliveries(conn, result["rows"], run_id)
    backup(state, day)
    _finish(args, text, f"New-term radar {day}")
    return 0


def keyword_table(cfg: dict, state: Path, names: list[str], repos: dict[str, str]) -> tuple[dict, str]:
    """The keyword table for names someone asked about: (the data, the table in Markdown)."""
    asked = [n.lower().strip() for n in names if n.strip()]
    conn = store.connect(state)
    signals = {n: store.signals_for(conn, n) for n in asked}     # the same leading rule as daily
    uc = usecases.run(cfg, state, asked, {k.lower(): v for k, v in repos.items()}, on_request=True,
                      signals=signals)
    return uc, "\n".join(report.keyword_table(cfg, uc)).strip() + "\n"


def kept_leads(state: Path, days: int, windows: dict | None = None) -> dict:
    conn = store.connect(state)
    return {"leads": store.leads(conn, days), "hit_rates": store.summary(conn, windows=windows)}


def cmd_slow(args, cfg: dict, state: Path) -> int:
    started = datetime.now().isoformat(timespec="seconds")
    result = slow.run(cfg, state, paid=not args.free)
    text = report.slow(cfg, result)
    if args.out:
        Path(args.out).write_text(text)
        Path(args.out).with_suffix(".json").write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str))
    print(text)
    conn = store.connect(state)
    run(lambda: {"run": store.record_run(
        conn, "slow", started, datetime.now().isoformat(timespec="seconds"), result["cost_micros"],
        {"rows": len(result["rows"]), "candidates": result["candidates"], "paid": result["paid"]},
        [*result["errors"], *result["paid_errors"]])})
    return 0


def cmd_precision(args, cfg: dict, state: Path) -> int:
    started = datetime.now().isoformat(timespec="seconds")
    conn = store.connect(state)
    result = precision.run(cfg, conn, n=args.n)
    out = json.dumps(result, ensure_ascii=False, indent=1, default=str) if args.json \
        else report.precision_sample(cfg, result)
    if args.out:
        Path(args.out).write_text(out)
    print(out)
    counts = {label: sum(1 for r in result["sampled"] if r["label"] == label)
              for label in ("new", "searched", "unknown")}
    run(lambda: {"run": store.record_run(
        conn, "precision", started, datetime.now().isoformat(timespec="seconds"), result["cost_micros"],
        {"sampled": len(result["sampled"]), **counts}, result["errors"])})
    return 0


def cmd_deliveries(args, state: Path) -> int:
    """What was delivered, by day: the history the `deliveries` table exists for."""
    conn = store.connect(state)
    rows = store.deliveries(conn, args.days, include_today=True)
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=1, default=str))
        return 0
    for row in rows:
        print(f"{row['day']}  {row['source']:<7} {row['term']:<28} {row['kind']:<5} {row['keyword']}")
    print(f"{len(rows)} rows in the last {args.days} days")
    return 0


def cmd_keywords(args, cfg: dict, state: Path) -> int:
    started = datetime.now().isoformat(timespec="seconds")
    repos = dict(r.split("=", 1) for r in args.repo)
    uc, text = keyword_table(cfg, state, args.names, repos)
    out = json.dumps(uc, ensure_ascii=False, indent=1, default=str) if args.json else text
    if args.out:
        Path(args.out).write_text(out)
    print(out)
    cost = uc.get("cost_micros") or 0
    print(t("cost", cost=f"${cost / 1e6:.3f}"), file=sys.stderr)   # keep the JSON body clean
    conn = store.connect(state)
    run(lambda: {"run": store.record_run(conn, "keywords", started,
                                         datetime.now().isoformat(timespec="seconds"), cost,
                                         {"names": len(args.names)}, [])})
    return 0


def cmd_pains(args, cfg: dict) -> int:
    keyword = " ".join(args.names).strip()
    if not keyword:
        raise SystemExit('pains: give a keyword, e.g. python -m radar pains "ai headshot"')
    result = pains.run(cfg, keyword, args.extension)
    out = json.dumps(result, ensure_ascii=False, indent=1, default=str) if args.json else report.pains(result)
    if args.out:
        Path(args.out).write_text(out)
    print(out)
    return 0


def cmd_leads(args, state: Path) -> int:
    data = kept_leads(state, args.days)
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=1, default=str))
        return 0
    for r in data["leads"]:
        verdict = f" · {r['verdict']}" + (f" ({r['days_ahead']} days ahead)" if r["days_ahead"] is not None else "") if r["verdict"] else ""
        print(f"{r['first_seen']}  {r['term']}  [{', '.join(r['signals'])}]{verdict}  {r['note']}")
    rates = data["hit_rates"]
    for lane, windows in rates["windows"].items():
        for days, by_signal in windows.items():
            for kind, s in by_signal.items():
                if not s["checked"]:
                    continue
                strong = f"{s['real']}/{s['scored']}" if s["scored"] else t("dash")
                if int(days) < review.TRENDS_FROM:      # a free window has no search_rise
                    again = f"{s['again']}/{s['seen']}" if s["seen"] else t("dash")
                    print(f"{lane} {days}d {kind}: strong {strong}, again {again}")
                else:
                    lead = s["median_lead"] if s["median_lead"] is not None else t("dash")
                    print(f"{lane} {days}d {kind}: hit {s['hit']}/{s['checked']}, strong {strong}, lead {lead}")
    for source, s in (rates.get("samples") or {}).items():
        print(f"{source} precision: {s['new']}/{s['sampled']} new ({s['searched']} searched, {s['unknown']} unknown)")
    waits = ", ".join(f"{lane} {days}d {n}" for lane, w in rates["pending_windows"].items() for days, n in w.items())
    print(f"{len(data['leads'])} leads in the last {args.days} days; waiting: {waits}")
    return 0


def serve_mcp() -> int:
    """`new-term-radar mcp`: the stdio MCP server under the package's own name, so a
    client that only knows the PyPI name can start it (`uvx --with mcp new-term-radar mcp`)."""
    try:
        from . import mcp_server
    except ImportError:
        print('The MCP server needs the `mcp` package: pip install "new-term-radar[mcp]"', file=sys.stderr)
        return 1
    mcp_server.main()
    return 0


def main(argv: list[str] | None = None) -> int:
    if not os.environ.get("RADAR_SKIP_ENV_FILE"):
        env.load(Path(__file__).resolve().parent.parent / ".env")
    if (sys.argv[1:] if argv is None else argv)[:1] == ["mcp"]:
        return serve_mcp()
    prog = "python -m radar" if __package__ == "radar" else "new-term-radar"  # installed, the package has another name
    p = argparse.ArgumentParser(prog=prog, description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["daily", "sources", "slow", "precision", "keywords", "deliveries", "leads", "pains"])
    p.add_argument("names", nargs="*", help="for `keywords`: the names to read")
    p.add_argument("--repo", action="append", default=[], metavar="NAME=OWNER/REPO", help="for `keywords`: a name's GitHub repository")
    p.add_argument("--days", type=int, default=7, help="for `leads`: how far back")
    p.add_argument("--json", action="store_true", help="for `keywords`, `leads` and `precision`: print JSON")
    p.add_argument("--n", type=int, help="for `precision`: how many candidates to sample (default: config)")
    p.add_argument("--config", default="config.json")
    p.add_argument("--state", default="state", help="directory for radar.db and the snapshots")
    p.add_argument("--out", help="write the report (Markdown) here; `daily` also writes a .json beside it")
    p.add_argument("--skip", default="", help="comma-separated: " + ",".join(sorted(SKIPPABLE)))
    p.add_argument("--extension", action="append", default=[], metavar="ID", help="for `pains`: a Chrome extension to read the reviews of")
    p.add_argument("--mail", action="store_true", help="mail the report (see radar/notify.py)")
    p.add_argument("--free", action="store_true", help="for `slow`: skip every paid step and list the candidates")
    args = p.parse_args(argv)
    args.skip = {s for s in args.skip.split(",") if s}
    unknown = args.skip - SKIPPABLE
    if unknown:
        p.error(f"--skip: unknown {sorted(unknown)}")
    state = Path(args.state)
    if args.command == "leads":
        return cmd_leads(args, state)
    if args.command == "deliveries":
        return cmd_deliveries(args, state)
    if args.command == "keywords" and not args.names:
        p.error("keywords: give at least one name")
    cfg = config.load(Path(args.config))
    state.mkdir(parents=True, exist_ok=True)
    if args.command == "keywords":
        return cmd_keywords(args, cfg, state)
    if args.command == "pains":
        return cmd_pains(args, cfg)
    if args.command == "slow":
        return cmd_slow(args, cfg, state)
    if args.command == "precision":
        return cmd_precision(args, cfg, state)
    return cmd_sources(args, cfg, state) if args.command == "sources" else cmd_daily(args, cfg, state)


if __name__ == "__main__":
    sys.exit(main())
