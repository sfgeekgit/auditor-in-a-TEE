"""`auditor run` — execute a plan."""

from __future__ import annotations

import argparse
import json

from .. import state
from ..api import Client
from .results import _render_results


def run(args: argparse.Namespace) -> int:
    plan_id = state.resolve_plan_id(args.plan_id)
    url = state.resolve_url(args.url)
    with Client(url) as c:
        resp = c.run(plan_id)

    if args.json_output:
        print(json.dumps(resp, indent=2))
        return 0

    print(f"Plan {plan_id} status: {resp['status']}")
    _render_results(resp.get("results", []))
    return 0
