"""One-off: fold the twin terms the migration left behind, and mark the URL echoes.

The migration copied one lead to one term, so a name the old table stored under two spellings
became two rows ("mirelo sfx" and "mirelo sfx 2.0"). Each twin would be reviewed, and paid for,
on its own on 2026-10-31. Rows a sitemap alone found are kept but marked `echo`, so no review
budget is spent on a name that already exists (bitbucket, zotero).

  python scripts/merge_terms.py --dry-run
  python scripts/merge_terms.py --apply

Signals and reviews move with the kept row; no row is deleted except the twin's own shell.
"""
import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from radar import store


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", type=Path, default=ROOT / "state" / "radar.db")
    ap.add_argument("--apply", action="store_true", help="write the changes; without it, only report")
    ap.add_argument("--dry-run", action="store_true", help="report the pairs and change nothing (the default)")
    args = ap.parse_args()
    args.apply = args.apply and not args.dry_run

    conn = sqlite3.connect(args.db)
    conn.execute(store.SCHEMA)
    conn.executescript(store.SCHEMA_NEXT)

    merged = 0
    while True:
        pairs = store.twins(conn)
        if not pairs:
            break
        for keep, drop in pairs:
            names = conn.execute("SELECT canonical FROM terms WHERE id IN (?, ?) ORDER BY first_seen",
                                 (keep, drop)).fetchall()
            print(f"merge {names[0][0]!r} <- {names[1][0]!r}")
            if args.apply:
                store.merge_terms(conn, keep, drop)
                merged += 1
        if not args.apply:
            break

    echoes = len(store.echo_ids(conn))
    print(f"twins merged: {merged}; url echoes to mark: {echoes}")
    if args.apply:
        print(f"marked echo: {store.mark_echoes(conn)}")
        print(f"terms left: {conn.execute('SELECT count(*) FROM terms').fetchone()[0]},"
              f" twins left: {len(store.twins(conn))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
