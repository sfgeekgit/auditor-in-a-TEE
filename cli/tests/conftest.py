"""Shared pytest fixtures.

The CLI repo lives at auditor-in-a-TEE/cli/. The server's webapp/ is a sibling
directory. We add it to sys.path so tests can import the server's canonical.py
to assert byte-for-byte agreement with the CLI's vendored copy.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

CLI_ROOT = Path(__file__).resolve().parents[1]
WEBAPP_DIR = CLI_ROOT.parent / "webapp"

# Make the server's canonical.py importable as `server_canonical`.
sys.path.insert(0, str(WEBAPP_DIR))


@pytest.fixture
def fixture_plan_dict() -> dict:
    """A plan dict in the shape both canonicalizers accept."""
    return {
        "name": "Test plan",
        "user1_public_key": "a" * 64,
        "user2_public_key": "b" * 64,
        "data1_format": {"description": "d1", "schema_hint": "text"},
        "data2_format": {"description": "d2", "schema_hint": "text"},
        "steps": [
            {"type": "run_python", "code": "result = data1 + data2"},
            {
                "type": "run_llm",
                "prompt": "Review {step_0_output} under {constitution}",
                "constitution": "rule 1: be honest",
                "model": "gemma4-31b",
            },
        ],
        "scripts": None,
    }
