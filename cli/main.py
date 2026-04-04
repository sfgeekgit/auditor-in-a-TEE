"""
CLI tool for auditor-in-a-TEE.

Usage:
  auditor-tee keygen                            Generate a new Ed25519 keypair
  auditor-tee view <plan_id>                    View a plan
  auditor-tee sign <plan_id> --as user1|user2 --private-key <hex>
  auditor-tee upload <plan_id> --as user1|user2 --private-key <hex> --file <path>
  auditor-tee upload <plan_id> --as user1|user2 --private-key <hex> --data <string>
  auditor-tee run <plan_id>                     Execute the plan
  auditor-tee results <plan_id>                 Get results
"""

import argparse
import os
import sys

from .client import AuditorClient
from .crypto import generate_keypair, sign, public_key_from_private


DEFAULT_API_URL = os.environ.get("AUDITOR_TEE_URL", "http://localhost:8080")


def format_plan(plan: dict) -> str:
    lines = []
    lines.append(f"Plan: {plan['name']} (ID: {plan['id']})")
    lines.append(f"Status: {plan['status']}")
    lines.append(f"Hash: {plan['plan_hash']}")
    lines.append("")
    lines.append("Data Formats:")
    lines.append(f"  User 1: {plan['data1_format']['description']}")
    lines.append(f"  User 2: {plan['data2_format']['description']}")
    lines.append("")
    lines.append("Steps:")
    for i, step in enumerate(plan["steps"]):
        if step["type"] == "run_python":
            code_preview = (step.get("code") or step.get("script") or "")[:100]
            lines.append(f"  [{i}] run_python: {code_preview}...")
        elif step["type"] == "run_llm":
            prompt_preview = (step.get("prompt") or "")[:100]
            lines.append(f"  [{i}] run_llm: {prompt_preview}...")
    lines.append("")
    if plan.get("scripts"):
        lines.append("Scripts:")
        for name in plan["scripts"]:
            lines.append(f"  - {name}")
        lines.append("")
    lines.append("Signatures:")
    for uid, sig in plan.get("signatures", {}).items():
        lines.append(f"  {uid}: {sig['public_key']}")
    if not plan.get("signatures"):
        lines.append("  (none yet)")
    lines.append("")
    lines.append("Data submitted:")
    for uid in plan.get("data_submitted", {}):
        lines.append(f"  {uid}: yes")
    if not plan.get("data_submitted"):
        lines.append("  (none yet)")
    return "\n".join(lines)


def format_results(results: dict) -> str:
    lines = []
    lines.append(f"Status: {results['status']}")
    lines.append("")
    for r in results["results"]:
        lines.append(f"--- Step {r['step']}: {r['type']} [{r['status']}] ---")
        if r.get("result"):
            lines.append(r["result"])
        if r.get("error"):
            lines.append(f"ERROR: {r['error']}")
        if r.get("stdout"):
            lines.append(f"[stdout]: {r['stdout']}")
        lines.append("")
    return "\n".join(lines)


def cmd_keygen(args, client):
    private_hex, public_hex = generate_keypair()
    print(f"Private key (keep secret): {private_hex}")
    print(f"Public key (share this):   {public_hex}")
    print()
    print("Save your private key securely. You will need it to sign plans and upload data.")


def cmd_view(args, client):
    plan = client.get_plan(args.plan_id)
    print(format_plan(plan))


def cmd_sign(args, client):
    # Derive public key from private key
    public_key = public_key_from_private(args.private_key)

    # Show the plan first for review
    plan = client.get_plan(args.plan_id)
    print("=== Plan to sign ===")
    print(format_plan(plan))
    print("====================")
    print()
    print(f"Your public key: {public_key}")
    print()

    confirm = input(f"Sign this plan as {args.user_id}? [y/N] ")
    if confirm.lower() != "y":
        print("Aborted.")
        return

    # Sign the plan hash with private key
    signature = sign(args.private_key, plan["plan_hash"])

    result = client.sign_plan(args.plan_id, args.user_id, public_key, signature)
    print(f"Signed. Status: {result['status']}")
    print(f"Signed by: {', '.join(result['signed_by'])}")


def cmd_upload(args, client):
    # Derive public key from private key
    public_key = public_key_from_private(args.private_key)

    if args.file:
        with open(args.file, "r") as f:
            data = f.read()
        print(f"Read {len(data)} bytes from {args.file}")
    elif args.data:
        data = args.data
    else:
        print("Error: --file or --data is required", file=sys.stderr)
        sys.exit(1)

    # Show a preview
    preview = data[:200] + ("..." if len(data) > 200 else "")
    print(f"Data preview:\n{preview}\n")

    confirm = input(f"Submit this data as {args.user_id}? [y/N] ")
    if confirm.lower() != "y":
        print("Aborted.")
        return

    result = client.submit_data(args.plan_id, args.user_id, data, public_key)
    print(f"Submitted. Status: {result['status']}")
    print(f"Data submitted by: {', '.join(result['data_submitted_by'])}")


def cmd_run(args, client):
    confirm = input("Run the computation? [y/N] ")
    if confirm.lower() != "y":
        print("Aborted.")
        return

    print("Running...")
    result = client.run(args.plan_id)
    print(format_results(result))


def cmd_results(args, client):
    result = client.get_results(args.plan_id)
    print(format_results(result))


def main():
    parser = argparse.ArgumentParser(
        prog="auditor-tee",
        description="CLI for auditor-in-a-TEE: multi-party computation in a Trusted Execution Environment",
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_API_URL,
        help=f"API URL (default: {DEFAULT_API_URL}, or set AUDITOR_TEE_URL env var)",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # keygen
    sub.add_parser("keygen", help="Generate a new Ed25519 keypair")

    # view
    p_view = sub.add_parser("view", help="View a plan")
    p_view.add_argument("plan_id")

    # sign
    p_sign = sub.add_parser("sign", help="Sign a plan")
    p_sign.add_argument("plan_id")
    p_sign.add_argument("--as", dest="user_id", required=True, choices=["user1", "user2"])
    p_sign.add_argument("--private-key", required=True, help="Your Ed25519 private key (hex)")

    # upload
    p_upload = sub.add_parser("upload", help="Upload private data")
    p_upload.add_argument("plan_id")
    p_upload.add_argument("--as", dest="user_id", required=True, choices=["user1", "user2"])
    p_upload.add_argument("--private-key", required=True, help="Your Ed25519 private key (hex)")
    p_upload.add_argument("--file", help="Path to data file")
    p_upload.add_argument("--data", help="Data string (alternative to --file)")

    # run
    p_run = sub.add_parser("run", help="Execute the plan")
    p_run.add_argument("plan_id")

    # results
    p_results = sub.add_parser("results", help="Get results")
    p_results.add_argument("plan_id")

    args = parser.parse_args()
    client = AuditorClient(args.url)

    commands = {
        "keygen": cmd_keygen,
        "view": cmd_view,
        "sign": cmd_sign,
        "upload": cmd_upload,
        "run": cmd_run,
        "results": cmd_results,
    }
    commands[args.command](args, client)


if __name__ == "__main__":
    main()
