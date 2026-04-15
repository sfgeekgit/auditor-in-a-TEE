"""`auditor plan {create,show,sign,template}` subcommands."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from importlib import resources
from pathlib import Path

from .. import state
from ..api import Client
from ..canonical import canonical_plan_bytes, plan_hash_hex
from ..keys import load_keypair, resolve_key_path
from ..plan_file import load_plan_file


def _emit(args: argparse.Namespace, human: str, obj: dict) -> None:
    if getattr(args, "json_output", False):
        print(json.dumps(obj, indent=2))
    else:
        print(human)


def run_create(args: argparse.Namespace) -> int:
    plan = load_plan_file(Path(args.file).expanduser())
    body = plan.to_create_request()

    # Compute canonical hash locally so we can cross-check the server.
    local_hash = plan_hash_hex(body)

    url = state.resolve_url(args.url)
    with Client(url) as c:
        resp = c.create_plan(body)

    if resp["plan_hash"].lower() != local_hash.lower():
        print(
            "error: plan_hash mismatch between CLI and server — schema drift between "
            f"cli/canonical.py and webapp/canonical.py?\n  local:  {local_hash}\n  server: {resp['plan_hash']}",
            file=sys.stderr,
        )
        return 1

    state.save(
        plan_id=resp["plan_id"],
        plan_hash=resp["plan_hash"],
        url=url,
        name=plan.name,
    )

    human = (
        f"Plan created\n"
        f"  plan_id:   {resp['plan_id']}\n"
        f"  plan_hash: {resp['plan_hash']}\n"
        f"  name:      {plan.name}\n"
        f"  url:       {url}\n"
        f"  state:     ./.auditor/state.json"
    )
    _emit(args, human, resp)
    return 0


def run_show(args: argparse.Namespace) -> int:
    plan_id = args.plan_id or state.resolve_plan_id(None)
    url = state.resolve_url(args.url)
    with Client(url) as c:
        plan = c.get_plan(plan_id)

    if args.json_output:
        print(json.dumps(plan, indent=2))
        return 0

    sig1 = "signed" if "user1" in plan.get("signatures", {}) else "pending"
    sig2 = "signed" if "user2" in plan.get("signatures", {}) else "pending"
    d1 = "submitted" if plan.get("data_submitted", {}).get("user1") else "pending"
    d2 = "submitted" if plan.get("data_submitted", {}).get("user2") else "pending"
    ek = plan.get("expected_keys", {})
    lines = [
        f"Plan {plan['id']}: {plan['name']}",
        f"  status:    {plan['status']}",
        f"  plan_hash: {plan['plan_hash']}",
        f"  user1 pk:  {ek.get('user1', '—')}   [{sig1}] data [{d1}]",
        f"  user2 pk:  {ek.get('user2', '—')}   [{sig2}] data [{d2}]",
        f"  steps:     {len(plan.get('steps', []))}",
        f"  results:   {'yes' if plan.get('has_results') else 'no'}",
    ]
    print("\n".join(lines))
    return 0


def run_sign(args: argparse.Namespace) -> int:
    plan_id = state.resolve_plan_id(args.plan_id)
    url = state.resolve_url(args.url)
    kp = load_keypair(resolve_key_path(args.key))

    with Client(url) as c:
        plan = c.get_plan(plan_id)

    expected = plan.get("expected_keys", {}).get(args.user)
    if not expected:
        print(f"error: plan does not declare an expected key for {args.user}", file=sys.stderr)
        return 1
    if expected.lower() != kp.public_key_hex.lower():
        print(
            f"error: your key ({kp.public_key_hex}) does not match the plan's "
            f"expected key for {args.user} ({expected}). Use the correct --key or "
            f"ask the plan creator to update the plan.",
            file=sys.stderr,
        )
        return 1

    # Reconstruct the canonical plan dict from the fetched view. We sign what
    # the server stored, not our local YAML.
    server_view = {
        "name": plan["name"],
        "user1_public_key": plan["expected_keys"]["user1"],
        "user2_public_key": plan["expected_keys"]["user2"],
        "data1_format": plan["data1_format"],
        "data2_format": plan["data2_format"],
        "steps": plan["steps"],
        "scripts": plan.get("scripts"),
    }
    if plan_hash_hex(server_view).lower() != plan["plan_hash"].lower():
        print(
            "error: canonical hash mismatch between fetched plan and server plan_hash — "
            "refusing to sign. Report this as a server bug.",
            file=sys.stderr,
        )
        return 1

    signature = kp.sign(canonical_plan_bytes(server_view))

    with Client(url) as c:
        resp = c.sign(
            plan_id,
            {
                "user_id": args.user,
                "public_key": kp.public_key_hex,
                "signature": signature,
            },
        )

    human = (
        f"Signed plan {plan_id} as {args.user}\n"
        f"  status:    {resp['status']}\n"
        f"  signed_by: {', '.join(resp.get('signed_by', []))}"
    )
    _emit(args, human, resp)
    return 0


def run_template(args: argparse.Namespace) -> int:
    tpl = resources.files("auditor_cli").joinpath("templates", f"{args.name}.yaml")
    if not tpl.is_file():
        print(f"error: template {args.name} not found in package", file=sys.stderr)
        return 1

    out = Path(args.out).expanduser() if args.out else Path(f"{args.name}.yaml")
    if out.exists() and not args.force:
        print(f"error: {out} already exists (use --force to overwrite)", file=sys.stderr)
        return 1

    with resources.as_file(tpl) as src:
        shutil.copyfile(src, out)

    print(f"Wrote template to {out}")
    print("Next: edit user1_public_key and user2_public_key, then `auditor plan create`")
    return 0
