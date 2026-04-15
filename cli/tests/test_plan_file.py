"""Plan-file YAML validation."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from auditor_cli.plan_file import load_plan_file


def test_load_valid_yaml(tmp_path: Path):
    plan_yaml = tmp_path / "plan.yaml"
    plan_yaml.write_text(
        """
name: Test
user1_public_key: "{pk1}"
user2_public_key: "{pk2}"
data1_format:
  description: d1
data2_format:
  description: d2
steps:
  - type: run_python
    code: "result = 1"
""".format(pk1="a" * 64, pk2="b" * 64)
    )
    p = load_plan_file(plan_yaml)
    assert p.name == "Test"
    assert len(p.steps) == 1
    assert p.steps[0].type == "run_python"


def test_load_rejects_short_pubkey(tmp_path: Path):
    plan_yaml = tmp_path / "plan.yaml"
    plan_yaml.write_text(
        """
name: Test
user1_public_key: "short"
user2_public_key: "also short"
data1_format: {description: d1}
data2_format: {description: d2}
steps: []
"""
    )
    with pytest.raises(ValidationError):
        load_plan_file(plan_yaml)


def test_load_rejects_missing_required(tmp_path: Path):
    plan_yaml = tmp_path / "plan.yaml"
    plan_yaml.write_text(
        """
name: Test
data1_format: {description: d1}
data2_format: {description: d2}
steps: []
"""
    )
    with pytest.raises(ValidationError):
        load_plan_file(plan_yaml)


def test_shipped_templates_are_valid():
    """The templates bundled in src/auditor_cli/templates must load cleanly."""
    from importlib import resources

    for name in ("salary", "openai_audit"):
        path = resources.files("auditor_cli").joinpath("templates", f"{name}.yaml")
        with resources.as_file(path) as p:
            load_plan_file(Path(p))
