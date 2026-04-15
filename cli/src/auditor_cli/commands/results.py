"""`auditor results` — fetch and render execution results."""

from __future__ import annotations

import argparse
import json

from .. import state
from ..api import Client


def _render_results(results: list[dict]) -> None:
    if not results:
        print("  (no results)")
        return
    for r in results:
        header = f"[step {r.get('step')}] {r.get('type')} — {r.get('status')}"
        print()
        print(header)
        print("-" * len(header))
        if r.get("status") == "error":
            print(f"error: {r.get('error', 'unknown')}")
        else:
            result = r.get("result", "")
            if isinstance(result, str) and len(result) > 2000:
                print(result[:2000])
                print(f"... [{len(result) - 2000} more chars truncated; use --json for full]")
            else:
                print(result)
            if r.get("stdout"):
                print("--- stdout ---")
                print(r["stdout"])


def run(args: argparse.Namespace) -> int:
    plan_id = state.resolve_plan_id(args.plan_id)
    url = state.resolve_url(args.url)
    with Client(url) as c:
        resp = c.results(plan_id)

    if args.json_output:
        print(json.dumps(resp, indent=2))
        return 0

    print(f"Plan {plan_id} status: {resp['status']}")
    _render_results(resp.get("results", []))
    return 0
