"""YAML/JSON plan-file loader with pydantic validation.

Mirrors the server's CreatePlanRequest shape without importing it, so the CLI
stays installable without FastAPI. tests/test_canonical_contract.py asserts the
two models produce the same canonical bytes on a fixture.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field


class DataFormat(BaseModel):
    description: str
    schema_hint: str = "text"


class Step(BaseModel):
    type: str
    prompt: Optional[str] = None
    constitution: Optional[str] = None
    model: Optional[str] = None
    max_tokens: Optional[int] = 1000
    script: Optional[str] = None
    code: Optional[str] = None
    inputs: Optional[list[str]] = None


class PlanFile(BaseModel):
    name: str
    user1_public_key: str = Field(min_length=64, max_length=64)
    user2_public_key: str = Field(min_length=64, max_length=64)
    data1_format: DataFormat
    data2_format: DataFormat
    steps: list[Step]
    scripts: Optional[dict[str, str]] = None
    tinfoil_api_key: Optional[str] = None

    def to_create_request(self) -> dict:
        """Serialize to the shape POST /plan expects."""
        return self.model_dump()


def load_plan_file(path: Path) -> PlanFile:
    text = path.read_text()
    if path.suffix in (".yml", ".yaml"):
        data: Any = yaml.safe_load(text)
    elif path.suffix == ".json":
        data = json.loads(text)
    else:
        # Best-effort: try YAML (it handles JSON too).
        data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError(f"plan file must be a mapping, got {type(data).__name__}")
    return PlanFile.model_validate(data)
