"""Check the benchmark basket once a month and cache each usable term's daily searches.

  python scripts/bench_check.py --dry-run
  python scripts/bench_check.py --apply

A benchmark earns its place with three checks (docs/05 §4.3 C): a Trends slope within +-20% over
the quarter, month-over-month volume within +-30%, and no single day above three times its median.
Fewer than two usable terms leaves every nameless name `uncalibrated` rather than guessed -- so run
this before trusting a size, and re-run it monthly (the volume data is monthly anyway).
"""
import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from radar import benchmarks, config, snap, usecases


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", type=Path, default=ROOT / "config.json")
    ap.add_argument("--state", type=Path, default=ROOT / "state")
    ap.add_argument("--apply", action="store_true", help="write state/benchmarks.json.gz")
    ap.add_argument("--dry-run", action="store_true", help="report only (the default)")
    args = ap.parse_args()
    args.apply = args.apply and not args.dry_run

    cfg = config.load(args.config)
    c = cfg["usecases"]
    terms = [b["term"] if isinstance(b, dict) else b for b in c["benchmarks"]]
    categories = {(b.get("category") if isinstance(b, dict) else "") for b in c["benchmarks"]}
    today = date.today()

    solo, cost = usecases.solo_series(terms, today)
    vol, cost2 = usecases.volumes(terms, c["location_code"])
    checked = {}
    for term in terms:
        months = (vol.get(term) or {}).get("months") or []
        result = benchmarks.drift(solo.get(term) or [], months, today)
        daily = benchmarks.daily((vol.get(term) or {}).get("volume") or 0) if result["ok"] else None
        if result["ok"] and not daily:
            result = {"ok": False, "reason": "no volume"}
        checked[term] = {**result, "daily": daily}
        print(f"{term:24s} {'ok' if result['ok'] else 'out':3s} {result['reason']:32s} {daily or ''}")

    ok = benchmarks.usable(checked)
    print(f"\nusable: {len(ok)}/{len(terms)}; categories in the basket: {len(categories - {''})}")
    print(f"spent on data: ${(cost + cost2) / 1e6:.3f}")
    if len(ok) < benchmarks.MIN_BENCHMARKS:
        print("fewer than 2 usable benchmarks: names will be sized uncalibrated")
    if args.apply:
        snap.save(args.state / "benchmarks.json.gz", {"checked_at": today.isoformat(), "terms": checked})
        print(f"wrote {args.state / 'benchmarks.json.gz'}")
    else:
        print("dry run: nothing written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
