"""
DSL executor for the auditor agent.

Supports two command types:
  - run_python: execute a python script with inputs
  - run_llm: call an LLM with a prompt template filled with data
"""

import io
import sys
import traceback
import httpx
from typing import Any


TINFOIL_API_URL = "https://api.tinfoil.sh/v1/chat/completions"
DEFAULT_MODEL = "meta-llama/Llama-3.3-70B-Instruct"


def execute_plan(steps: list[dict], context: dict, tinfoil_api_key: str | None = None) -> list[dict]:
    """
    Execute a sequence of DSL steps.

    Args:
        steps: list of step dicts, each with 'type' and type-specific fields
        context: dict with 'data1', 'data2', and any uploaded 'scripts'
        tinfoil_api_key: API key for Tinfoil LLM calls

    Returns:
        list of result dicts, one per step
    """
    results = []
    step_outputs = {}

    for i, step in enumerate(steps):
        step_type = step.get("type")
        try:
            if step_type == "run_python":
                output = _run_python(step, context, step_outputs)
            elif step_type == "run_llm":
                output = _run_llm(step, context, step_outputs, tinfoil_api_key)
            else:
                output = {"error": f"Unknown step type: {step_type}"}

            step_outputs[f"step_{i}_output"] = output.get("result", "")
            results.append({"step": i, "type": step_type, "status": "success", **output})
        except Exception as e:
            err = {"step": i, "type": step_type, "status": "error", "error": str(e)}
            step_outputs[f"step_{i}_output"] = f"ERROR: {e}"
            results.append(err)

    return results


def _fill_template(template: str, context: dict, step_outputs: dict) -> str:
    """Fill {placeholders} in a template with context and prior step outputs."""
    merged = {**context, **step_outputs}
    # Only replace placeholders that exist in merged
    for key, val in merged.items():
        template = template.replace(f"{{{key}}}", str(val))
    return template


def _run_python(step: dict, context: dict, step_outputs: dict) -> dict:
    """Execute a python script in a restricted namespace."""
    script_name = step.get("script", "")
    scripts = context.get("scripts", {})

    if script_name and script_name in scripts:
        code = scripts[script_name]
    elif step.get("code"):
        code = step["code"]
    else:
        return {"error": f"Script '{script_name}' not found"}

    # Build namespace with inputs
    namespace = {
        "data1": context.get("data1", ""),
        "data2": context.get("data2", ""),
        "__builtins__": __builtins__,
    }
    # Add step outputs
    for k, v in step_outputs.items():
        namespace[k] = v
    # Add any explicit inputs
    for input_name in step.get("inputs", []):
        if input_name in context:
            namespace[input_name] = context[input_name]
        elif input_name in step_outputs:
            namespace[input_name] = step_outputs[input_name]

    # Capture stdout
    old_stdout = sys.stdout
    sys.stdout = captured = io.StringIO()

    try:
        exec(code, namespace)
    finally:
        sys.stdout = old_stdout

    stdout_output = captured.getvalue()
    # Look for a 'result' variable in namespace, fallback to stdout
    result = namespace.get("result", stdout_output.strip())

    return {"result": str(result), "stdout": stdout_output}


def _run_llm(step: dict, context: dict, step_outputs: dict, api_key: str | None) -> dict:
    """Call an LLM with a filled prompt template."""
    prompt_template = step.get("prompt", "")
    model = step.get("model", DEFAULT_MODEL)

    prompt = _fill_template(prompt_template, context, step_outputs)

    if not api_key:
        return {"result": f"[LLM call skipped - no API key]\nPrompt would be:\n{prompt}"}

    try:
        resp = httpx.post(
            TINFOIL_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": step.get("max_tokens", 1000),
            },
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        result = data["choices"][0]["message"]["content"]
        return {"result": result}
    except Exception as e:
        return {"result": f"LLM call failed: {e}", "error": str(e)}
