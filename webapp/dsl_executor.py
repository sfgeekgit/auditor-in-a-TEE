"""
DSL executor for the auditor agent.

Supports two command types:
  - run_python: execute a python script with inputs
  - run_llm: call an LLM with a prompt template filled with data
"""

import io
import logging
import os
import sys
import traceback
from typing import Any

# Replica change (no TEE): LLM calls go to OpenRouter via the OpenAI-compatible
# client instead of Tinfoil's enclave-attested TinfoilAI client.
from openai import OpenAI


log = logging.getLogger(__name__)

DEFAULT_MODEL = os.environ.get("MODEL_NAME", "gemma4-31b")
# Replica change: OPENROUTER_API_KEY replaces TINFOIL_API_KEY. The variable
# name is kept so api_server.py's import is unchanged.
TINFOIL_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
# Replica change: sampling knobs. The VALID/INVALID verdicts are noisy at the
# default temperature on cheap OpenRouter models, so default to temperature 0.
# LLM_REASONING=on lets a reasoning model think (needs LLM_MIN_MAX_TOKENS ~4000);
# off (default) asks OpenRouter to disable reasoning so max_tokens is not
# consumed before any answer is produced.
LLM_TEMPERATURE = float(os.environ.get("LLM_TEMPERATURE", "0"))
LLM_MIN_MAX_TOKENS = int(os.environ.get("LLM_MIN_MAX_TOKENS", "0"))
LLM_EXTRA_BODY = (
    None if os.environ.get("LLM_REASONING", "off").lower() == "on"
    else {"reasoning": {"enabled": False}}
)


def execute_steps(
    steps: list[dict],
    indices: list[int],
    context: dict,
    step_outputs: dict,
    tinfoil_api_key: str | None = None,
) -> list[dict]:
    """
    Execute a subset of a plan's steps (selected by index), mutating the shared
    `step_outputs` dict so later stages can reference earlier `{step_N_output}`
    placeholders.

    Args:
        steps: full list of step dicts (indices refer into this list)
        indices: which step positions to actually run this call
        context: dict with 'data1', 'data2', and any uploaded 'scripts'
        step_outputs: mutated in place; keyed as 'step_N_output'
        tinfoil_api_key: API key for Tinfoil LLM calls

    Returns:
        list of result dicts for the executed indices, in order
    """
    results = []
    for i in indices:
        step = steps[i]
        step_type = step.get("type")
        try:
            if step_type == "run_python":
                output = _run_python(step, context, step_outputs)
            elif step_type == "run_llm":
                output = _run_llm(step, context, step_outputs, tinfoil_api_key)
            else:
                output = {"result": "Step skipped: unknown type."}

            step_outputs[f"step_{i}_output"] = output.get("result") or ""
            results.append({"step": i, "type": step_type, "stage": step.get("stage"),
                            "status": "success", **output})
        except Exception:
            log.exception("Step %d (%s) failed", i, step_type)
            step_outputs[f"step_{i}_output"] = "Step failed."
            results.append({"step": i, "type": step_type, "stage": step.get("stage"),
                            "status": "error", "result": "Step failed."})

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
    scripts = context.get("scripts") or {}

    if script_name and script_name in scripts:
        code = scripts[script_name]
    elif step.get("code"):
        code = step["code"]
    else:
        return {"result": "Script execution failed."}

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
    for input_name in (step.get("inputs") or []):
        if input_name in context:
            namespace[input_name] = context[input_name]
        elif input_name in step_outputs:
            namespace[input_name] = step_outputs[input_name]

    # Capture stdout
    old_stdout = sys.stdout
    sys.stdout = captured = io.StringIO()

    try:
        exec(code, namespace)
    except Exception as e:
        # Log full error server-side, return generic message to users
        log.exception("Python step execution failed")
        return {"result": "Script execution failed."}
    finally:
        sys.stdout = old_stdout

    stdout_output = captured.getvalue()
    # Look for a 'result' variable in namespace, fallback to stdout
    result = namespace.get("result", stdout_output.strip())

    return {"result": str(result)}


def _run_llm(step: dict, context: dict, step_outputs: dict, api_key: str | None) -> dict:
    """Call an LLM with a filled prompt template."""
    prompt_template = step.get("prompt", "")
    # Replica change: plan steps name Tinfoil models (e.g. "gemma4-31b") that do
    # not exist on OpenRouter, so MODEL_NAME from the environment takes precedence.
    model = os.environ.get("MODEL_NAME") or step.get("model") or DEFAULT_MODEL

    # Per-step constitution is exposed as the {constitution} placeholder.
    llm_context = {**context, "constitution": step.get("constitution") or ""}
    prompt = _fill_template(prompt_template, llm_context, step_outputs)

    effective_key = TINFOIL_API_KEY or api_key
    if not effective_key:
        return {"result": f"[LLM call skipped - no API key]\nPrompt would be:\n{prompt}"}

    client = OpenAI(base_url=OPENROUTER_BASE_URL, api_key=effective_key)

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max(step.get("max_tokens") or 1000, LLM_MIN_MAX_TOKENS),
            temperature=LLM_TEMPERATURE,
            extra_body=LLM_EXTRA_BODY,
        )
        msg = resp.choices[0].message
        # Some models (reasoning models) put content in reasoning_content
        result = msg.content or getattr(msg, "reasoning_content", None) or ""
        return {"result": result}
    except Exception as e:
        log.exception("LLM call failed")
        return {"result": "LLM call failed."}
