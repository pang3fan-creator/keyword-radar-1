"""One paid DataForSEO whois query, for reading the error the daily run hides.

`aisa.call()` drops a failed tool call from the result and keeps going, so a rejected
filter looks like "no new sites". This script asks the router for the same task
new_sites.py builds and prints what came back: cost, whether the call was successful,
and the task's own status_code / status_message. One query, about $0.13.

    .venv/bin/python scripts/new_sites_probe.py [--query ai]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from radar import aisa, config, env, new_sites  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="config.json")
    p.add_argument("--query", help="which query to probe (default: the first)")
    args = p.parse_args()
    env.load(ROOT / ".env")
    cfg = config.load(ROOT / args.config)
    c = cfg["new_sites"]
    calls = new_sites._calls(c, date.today())
    calls = [call for call in calls if args.query is None or call["call_id"] == args.query][:1]
    if not calls:
        print(f"no such query: {args.query}")
        return 1
    body = aisa._post(aisa.ROUTER, {"calls": calls}, aisa.TIMEOUT)
    if "error" in body:
        print(f"router error: {body['error']}")
        return 1
    for result in body.get("results", []):
        cost = int(result.get("customer_cost_micros_usd") or 0)
        task = ((result.get("data") or {}).get("tasks") or [{}])[0]
        items = ((task.get("result") or [{}])[0] or {}).get("items") or []
        print(f"query {result.get('call_id')}: successful={result.get('successful')} cost=${cost / 1e6:.3f}")
        print(f"  status: {task.get('status_code')} {task.get('status_message') or task.get('status') or ''}".rstrip())
        print(f"  items: {len(items)}")
        if result.get("error"):
            print(f"  error: {json.dumps(result['error'])[:400]}")
        if items:
            print(f"  first: {json.dumps(items[0])[:400]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
