"""One-off: copy the old `leads` table into terms / term_signals / reviews / runs (docs/05 §5.1).

  python scripts/migrate_leads.py --dry-run
  python scripts/migrate_leads.py --run 2026-10-16=state/backup-2026-10-16/report.json \
      --run 2026-10-17=report.json --cost 2026-10-17=341000

`leads` is only read, never changed, and a term that is already in `terms` is skipped, so the
script can be re-run after a daily run added leads. The cost of a historical run is not stored
anywhere: pass it by hand, in micro-USD, or the run keeps cost_micros NULL.
"""
import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from radar import migrate, store


def _pairs(items: list[str], what: str) -> dict[str, str]:
    out = {}
    for item in items:
        if "=" not in item:
            raise SystemExit(f"--{what} wants KEY=VALUE, got {item!r}")
        key, value = item.split("=", 1)
        out[key] = value
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", type=Path, default=ROOT / "state" / "radar.db")
    ap.add_argument("--dry-run", action="store_true", help="report the counts, write nothing")
    ap.add_argument("--run", action="append", default=[], metavar="YYYY-MM-DD=REPORT",
                    help="a finished run to record, with the report.json it wrote (repeatable)")
    ap.add_argument("--cost", action="append", default=[], metavar="YYYY-MM-DD=MICROS",
                    help="its cost in micro-USD, when it is known (repeatable)")
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    conn.execute(store.SCHEMA)
    conn.commit()

    stats = migrate.migrate(conn, dry_run=args.dry_run)

    runs, costs = _pairs(args.run, "run"), _pairs(args.cost, "cost")
    if args.dry_run:
        for day, path in runs.items():
            print(f"run {day}: {migrate.read_report(Path(path))}")
        print(f"would copy {stats['terms']} term(s), {stats['signals']} signal(s),"
              f" {stats['reviews']} review(s), skip {stats['skipped']}")
        print("dry run: the new rows were rolled back")
        return 0

    recorded = 0
    for day, path in runs.items():
        cost = int(costs[day]) if day in costs else None
        recorded += 1 if migrate.add_run(conn, day, "daily", cost, migrate.read_report(Path(path))) else 0

    rep = migrate.reconcile(conn)
    print(f"leads {rep['leads']} -> terms {rep['terms']}, signals {rep['signals']}, reviews {rep['reviews']}")
    print(f"copied {stats['terms']} term(s), skipped {stats['skipped']}; runs recorded {recorded}")
    if rep["missing"]:
        print("did not arrive:", ", ".join(rep["missing"]))
    if rep["drift"]:
        print(f"{rep['drift']} term(s) drift from the lead they came from")
    if rep["missing"] or rep["drift"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
