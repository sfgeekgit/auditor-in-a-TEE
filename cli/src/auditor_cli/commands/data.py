"""`auditor data submit` — sign and submit private data."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .. import state
from ..api import Client
from ..canonical import submit_message
from ..keys import load_keypair, resolve_key_path


def _read_data(spec: str) -> str:
    if spec == "-":
        return sys.stdin.read()
    return Path(spec).expanduser().read_text()


def run_submit(args: argparse.Namespace) -> int:
    plan_id = state.resolve_plan_id(args.plan_id)
    url = state.resolve_url(args.url)
    kp = load_keypair(resolve_key_path(args.key))
    data = _read_data(args.data)

    with Client(url) as c:
        plan = c.get_plan(plan_id)

    expected = plan.get("expected_keys", {}).get(args.user)
    if not expected:
        print(f"error: plan does not declare an expected key for {args.user}", file=sys.stderr)
        return 1
    if expected.lower() != kp.public_key_hex.lower():
        print(
            f"error: your key ({kp.public_key_hex}) does not match the plan's "
            f"expected key for {args.user} ({expected}).",
            file=sys.stderr,
        )
        return 1

    signature = kp.sign(submit_message(plan["plan_hash"], data))

    with Client(url) as c:
        resp = c.submit_data(
            plan_id,
            {
                "user_id": args.user,
                "data": data,
                "public_key": kp.public_key_hex,
                "signature": signature,
            },
        )

    if args.json_output:
        print(json.dumps(resp, indent=2))
    else:
        print(f"Submitted data as {args.user}")
        print(f"  status:             {resp['status']}")
        print(f"  data_submitted_by:  {', '.join(resp.get('data_submitted_by', []))}")
    return 0
