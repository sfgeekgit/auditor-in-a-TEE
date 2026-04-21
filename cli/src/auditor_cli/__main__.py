"""argparse dispatcher for the `auditor` CLI."""

from __future__ import annotations

import argparse
import sys
from typing import Callable

from . import __version__
from .api import APIError
from .commands import data as data_cmd
from .commands import keygen as keygen_cmd
from .commands import plan as plan_cmd
from .commands import results as results_cmd
from .commands import run as run_cmd


def _url_arg(p: argparse.ArgumentParser) -> None:
    p.add_argument("--url", default=None, help="TEE server URL (overrides AUDITOR_TEE_URL / state)")


def _plan_id_arg(p: argparse.ArgumentParser) -> None:
    p.add_argument("--plan-id", default=None, help="Plan ID (overrides AUDITOR_PLAN_ID / state)")


def _key_arg(p: argparse.ArgumentParser) -> None:
    p.add_argument("--key", default=None, help="Path to keypair JSON (overrides AUDITOR_KEY; default ~/.auditor/keys/default.json)")


def _json_arg(p: argparse.ArgumentParser) -> None:
    p.add_argument("--json", dest="json_output", action="store_true", help="Emit JSON instead of human-readable output")


def _user_arg(p: argparse.ArgumentParser) -> None:
    p.add_argument("--user", required=True, choices=["user1", "user2"], help="Which party you are")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="auditor", description="CLI for the auditor-in-a-TEE service")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # keygen
    p_keygen = sub.add_parser("keygen", help="Generate an ed25519 keypair")
    p_keygen.add_argument("--out", default=None, help="Output path (default ~/.auditor/keys/default.json)")
    p_keygen.add_argument("--force", action="store_true", help="Overwrite if file exists")
    p_keygen.set_defaults(func=keygen_cmd.run)

    # plan
    p_plan = sub.add_parser("plan", help="Plan operations")
    p_plan_sub = p_plan.add_subparsers(dest="plan_cmd", required=True)

    p_plan_create = p_plan_sub.add_parser("create", help="Create a plan from a YAML/JSON file")
    p_plan_create.add_argument("file", help="Plan file path (YAML or JSON)")
    _url_arg(p_plan_create)
    _json_arg(p_plan_create)
    p_plan_create.set_defaults(func=plan_cmd.run_create)

    p_plan_show = p_plan_sub.add_parser("show", help="Fetch and display a plan")
    p_plan_show.add_argument("plan_id", nargs="?", default=None)
    _url_arg(p_plan_show)
    _json_arg(p_plan_show)
    p_plan_show.set_defaults(func=plan_cmd.run_show)

    p_plan_sign = p_plan_sub.add_parser("sign", help="Sign a plan as user1 or user2")
    _user_arg(p_plan_sign)
    _key_arg(p_plan_sign)
    _plan_id_arg(p_plan_sign)
    _url_arg(p_plan_sign)
    _json_arg(p_plan_sign)
    p_plan_sign.set_defaults(func=plan_cmd.run_sign)

    p_plan_tpl = p_plan_sub.add_parser("template", help="Write a built-in plan template to disk")
    p_plan_tpl.add_argument("name", choices=["salary", "openbrain_audit"])
    p_plan_tpl.add_argument("--out", default=None, help="Output path (default: <name>.yaml in CWD)")
    p_plan_tpl.add_argument("--force", action="store_true", help="Overwrite if file exists")
    p_plan_tpl.set_defaults(func=plan_cmd.run_template)

    # data
    p_data = sub.add_parser("data", help="Private data operations")
    p_data_sub = p_data.add_subparsers(dest="data_cmd", required=True)

    p_data_submit = p_data_sub.add_parser("submit", help="Submit your private data")
    _user_arg(p_data_submit)
    _key_arg(p_data_submit)
    _plan_id_arg(p_data_submit)
    _url_arg(p_data_submit)
    p_data_submit.add_argument("--data", required=True, help="Path to data file, or '-' for stdin")
    _json_arg(p_data_submit)
    p_data_submit.set_defaults(func=data_cmd.run_submit)

    # run
    p_run = sub.add_parser("run", help="Execute the plan")
    _plan_id_arg(p_run)
    _url_arg(p_run)
    _json_arg(p_run)
    p_run.set_defaults(func=run_cmd.run)

    # results
    p_results = sub.add_parser("results", help="Fetch results of a completed plan")
    _plan_id_arg(p_results)
    _url_arg(p_results)
    _json_arg(p_results)
    p_results.set_defaults(func=results_cmd.run)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    func: Callable[[argparse.Namespace], int] = args.func
    try:
        return func(args) or 0
    except APIError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except LookupError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except FileNotFoundError as e:
        print(f"error: file not found: {e}", file=sys.stderr)
        return 2
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
