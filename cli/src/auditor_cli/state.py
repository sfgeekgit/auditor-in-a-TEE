"""Per-directory CLI state at ./.auditor/state.json.

Written by `plan create`, read by every later command so that --plan-id and
--url don't have to be typed each time.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional


STATE_DIR_NAME = ".auditor"
STATE_FILE_NAME = "state.json"


def state_path(cwd: Optional[Path] = None) -> Path:
    return (cwd or Path.cwd()) / STATE_DIR_NAME / STATE_FILE_NAME


def load() -> dict:
    p = state_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def save(**fields) -> None:
    p = state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    existing = load()
    existing.update(fields)
    p.write_text(json.dumps(existing, indent=2) + "\n")


def resolve_plan_id(explicit: str | None) -> str:
    """Flag > env > state file > error."""
    if explicit:
        return explicit
    env = os.environ.get("AUDITOR_PLAN_ID")
    if env:
        return env
    s = load()
    if s.get("plan_id"):
        return s["plan_id"]
    raise LookupError(
        "no plan id provided; pass --plan-id, set AUDITOR_PLAN_ID, or run `auditor plan create` first"
    )


def resolve_url(explicit: str | None) -> str:
    """Flag > env > state file > error."""
    if explicit:
        return explicit.rstrip("/")
    env = os.environ.get("AUDITOR_TEE_URL")
    if env:
        return env.rstrip("/")
    s = load()
    if s.get("url"):
        return s["url"].rstrip("/")
    raise LookupError(
        "no TEE URL provided; pass --url or set AUDITOR_TEE_URL"
    )
