"""
FastAPI server for the auditor-in-a-TEE agent.

Two parties with private data agree on a computation plan,
submit their data to the TEE, and receive results.
"""

import os
import uuid
import time
from typing import Literal, Optional

import uvicorn
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from canonical import canonical_plan_bytes, plan_hash_hex, submit_message
from dsl_executor import execute_steps


STAGES: tuple[str, ...] = ("input", "query", "output")
Stage = Literal["input", "query", "output"]


# Strict signature verification is the default. Set REQUIRE_SIGNATURES=false
# in local dev if you want to exercise the flow without real keys.
REQUIRE_SIGS = os.getenv("REQUIRE_SIGNATURES", "true").lower() == "true"

app = FastAPI(
    title="Auditor-in-a-TEE API",
    description="Multi-party computation agent running in a Trusted Execution Environment",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Request / Response models ---

class DataFormat(BaseModel):
    description: str = Field(description="Human-readable description of what data is expected")
    schema_hint: str = Field(default="text", description="Expected format: text, json, csv")


class Step(BaseModel):
    type: str = Field(description="Step type: run_python or run_llm")
    stage: Stage = Field(description="Which pipeline stage this step belongs to: input, query, or output")
    title: str = Field(description="Short human-readable title for the step")
    description: Optional[str] = Field(default=None, description="One-paragraph description of what the step does")
    prompt: Optional[str] = Field(default=None, description="Prompt template for run_llm")
    constitution: Optional[str] = Field(default=None, description="Constitution text for run_llm, referenced as {constitution} in the prompt")
    model: Optional[str] = Field(default=None, description="Model name for run_llm")
    max_tokens: Optional[int] = Field(default=1000)
    script: Optional[str] = Field(default=None, description="Script name for run_python")
    code: Optional[str] = Field(default=None, description="Inline python code for run_python")
    inputs: Optional[list[str]] = Field(default=None, description="Input variable names for run_python")


class CreatePlanRequest(BaseModel):
    name: str = Field(description="Human-readable plan name")
    summary: Optional[str] = Field(default=None, description="One-paragraph description of what the plan does, shown in the UI")
    user1_public_key: str = Field(min_length=64, max_length=64, description="Expected ed25519 public key for user 1 (64 hex chars)")
    user2_public_key: str = Field(min_length=64, max_length=64, description="Expected ed25519 public key for user 2 (64 hex chars)")
    data1_format: DataFormat = Field(description="Expected format for user 1's data")
    data2_format: DataFormat = Field(description="Expected format for user 2's data")
    steps: list[Step] = Field(description="DSL steps to execute")
    scripts: Optional[dict[str, str]] = Field(default=None, description="Named python scripts (name -> code)")
    tinfoil_api_key: Optional[str] = Field(default=None, description="API key for Tinfoil LLM calls")


class SignRequest(BaseModel):
    user_id: str = Field(description="'user1' or 'user2'")
    public_key: str = Field(min_length=64, max_length=64, description="User's ed25519 public key (64 hex chars)")
    signature: str = Field(default="", description="ed25519 signature over canonical_plan_bytes (128 hex chars); required when REQUIRE_SIGNATURES=true")


class SubmitDataRequest(BaseModel):
    user_id: str = Field(description="'user1' or 'user2'")
    data: str = Field(description="The private data")
    public_key: str = Field(min_length=64, max_length=64, description="User's ed25519 public key (64 hex chars) — must match the key used at sign time")
    signature: str = Field(default="", description="ed25519 signature over submit_message(plan_hash, data); required when REQUIRE_SIGNATURES=true")


# --- In-memory storage ---

plans: dict[str, dict] = {}


# --- Endpoints ---

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/plan")
def create_plan(req: CreatePlanRequest):
    """Create a new audit plan. Returns the plan ID and hash."""
    plan_id = str(uuid.uuid4())[:8]

    plan = {
        "id": plan_id,
        "name": req.name,
        "summary": req.summary,
        "user1_public_key": req.user1_public_key,
        "user2_public_key": req.user2_public_key,
        "data1_format": req.data1_format.model_dump(),
        "data2_format": req.data2_format.model_dump(),
        "steps": [s.model_dump() for s in req.steps],
        # Store scripts as-sent so canonical_plan_bytes matches what the client signed.
        # The executor is tolerant of None.
        "scripts": req.scripts,
        "tinfoil_api_key": req.tinfoil_api_key,
        "signatures": {},
        "data": {},
        "previous_data": {},   # user_id -> prior submission, populated on appeals
        "results": None,
        "stage_status": {s: "pending" for s in STAGES},
        "stage_results": {s: None for s in STAGES},
        "step_outputs": {},
        "status": "created",
        "created_at": time.time(),
        "ledger": [],  # append-only event log — populated by _append_ledger
    }
    plan["plan_hash"] = plan_hash_hex(plan)

    plans[plan_id] = plan
    _append_ledger(plan, {"type": "plan_created", "name": req.name, "plan_id": plan_id})

    return {
        "plan_id": plan_id,
        "plan_hash": plan["plan_hash"],
        "status": "created",
    }


def _append_ledger(plan: dict, entry: dict) -> None:
    """
    Append a single entry to the plan's public ledger.
    Callers MUST NOT include any private data (query text, uploaded files, etc.)
    — the ledger is visible to both parties.
    """
    entry = dict(entry)
    entry.setdefault("timestamp", time.time())
    plan.setdefault("ledger", []).append(entry)


@app.post("/plans/reset")
def reset_plans():
    """
    Clear all in-memory plans. Intended for the demo webapp's 'Reset Server'
    button so a fresh run can start from a clean slate. Unauthenticated —
    acceptable while the TEE is publicly shared for this demo.
    """
    count = len(plans)
    plans.clear()
    return {"deleted": count}


@app.get("/plans")
def list_plans():
    """List all plans with summary info. Used by TEE operator dashboard."""
    return {
        "plans": [
            {
                "id": p["id"],
                "name": p["name"],
                "status": p["status"],
                "created_at": p["created_at"],
                "has_results": p["results"] is not None,
                "signed_by": list(p["signatures"].keys()),
                "data_submitted_by": list(p["data"].keys()),
                "expected_keys": {
                    "user1": p["user1_public_key"],
                    "user2": p["user2_public_key"],
                },
            }
            for p in sorted(plans.values(), key=lambda x: x["created_at"], reverse=True)
        ]
    }


@app.get("/plan/{plan_id}")
def get_plan(plan_id: str):
    """View a plan (both users can see this). Private data and API keys are not exposed."""
    plan = plans.get(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    return {
        "id": plan["id"],
        "name": plan["name"],
        "summary": plan.get("summary"),
        "data1_format": plan["data1_format"],
        "data2_format": plan["data2_format"],
        "steps": plan["steps"],
        "scripts": plan["scripts"],
        "plan_hash": plan["plan_hash"],
        "status": plan["status"],
        "stage_status": plan.get("stage_status", {s: "pending" for s in STAGES}),
        "ledger": plan.get("ledger", []),
        "expected_keys": {
            "user1": plan["user1_public_key"],
            "user2": plan["user2_public_key"],
        },
        "signatures": {k: {"public_key": v["public_key"][:16] + "..."} for k, v in plan["signatures"].items()},
        "data_submitted": {
            "user1": "user1" in plan["data"],
            "user2": "user2" in plan["data"],
        },
        "has_results": plan["results"] is not None,
    }


@app.post("/plan/{plan_id}/sign")
def sign_plan(plan_id: str, req: SignRequest):
    """Sign off on a plan. Each user can sign independently."""
    plan = plans.get(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    if req.user_id not in ("user1", "user2"):
        raise HTTPException(status_code=400, detail="user_id must be 'user1' or 'user2'")

    # Identity: the signer's pubkey must match the one committed at plan creation.
    expected_pk = plan["user1_public_key"] if req.user_id == "user1" else plan["user2_public_key"]
    if req.public_key.lower() != expected_pk.lower():
        raise HTTPException(status_code=403, detail=f"public_key does not match expected key for {req.user_id}")

    if REQUIRE_SIGS:
        if len(req.signature) != 128:
            raise HTTPException(status_code=400, detail="signature must be 128 hex chars (ed25519, 64 bytes)")
        try:
            pk = Ed25519PublicKey.from_public_bytes(bytes.fromhex(req.public_key))
            pk.verify(bytes.fromhex(req.signature), canonical_plan_bytes(plan))
        except (InvalidSignature, ValueError):
            raise HTTPException(status_code=403, detail="Invalid signature")

    already_signed = req.user_id in plan["signatures"]
    plan["signatures"][req.user_id] = {
        "public_key": req.public_key,
        "signature": req.signature,
        "signed_at": time.time(),
    }
    if not already_signed:
        _append_ledger(plan, {"type": "signed", "user_id": req.user_id})

    _update_plan_status(plan)

    return {
        "status": plan["status"],
        "signed_by": list(plan["signatures"].keys()),
    }


@app.post("/plan/{plan_id}/data")
def submit_data(plan_id: str, req: SubmitDataRequest):
    """Submit private data. The submitting user must have signed the plan first."""
    plan = plans.get(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    if req.user_id not in ("user1", "user2"):
        raise HTTPException(status_code=400, detail="user_id must be 'user1' or 'user2'")

    # The submitting user must have signed
    if req.user_id not in plan["signatures"]:
        raise HTTPException(status_code=400, detail=f"{req.user_id} must sign the plan before submitting data")

    # Public key must match the one used to sign (which in turn matched the plan's expected_keys).
    if plan["signatures"][req.user_id]["public_key"].lower() != req.public_key.lower():
        raise HTTPException(status_code=403, detail="Public key does not match the key used to sign the plan")

    if REQUIRE_SIGS:
        if len(req.signature) != 128:
            raise HTTPException(status_code=400, detail="signature must be 128 hex chars (ed25519, 64 bytes)")
        try:
            pk = Ed25519PublicKey.from_public_bytes(bytes.fromhex(req.public_key))
            pk.verify(
                bytes.fromhex(req.signature),
                submit_message(plan["plan_hash"], req.data),
            )
        except (InvalidSignature, ValueError):
            raise HTTPException(status_code=403, detail="Invalid data signature")

    first_upload = req.user_id not in plan["data"]
    plan["data"][req.user_id] = req.data
    if first_upload:
        _append_ledger(plan, {"type": "data_submitted", "user_id": req.user_id})
    _update_plan_status(plan)

    return {
        "status": plan["status"],
        "data_submitted_by": list(plan["data"].keys()),
    }


@app.get("/plan/{plan_id}/data/{user_id}")
def get_submitted_data(plan_id: str, user_id: str):
    """
    Return the raw uploaded data for a given user on a plan.

    NOTE: unauthenticated. Intended for the User 1 / User 2 pages in the
    demo webapp so each side can see what they submitted. Fine while the
    TEE is publicly shared for this demo; real deployments would gate
    this behind a signed challenge.
    """
    plan = plans.get(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    if user_id not in ("user1", "user2"):
        raise HTTPException(status_code=400, detail="user_id must be 'user1' or 'user2'")

    if user_id not in plan["data"]:
        return {"submitted": False, "data": None}

    return {
        "submitted": True,
        "data": plan["data"][user_id],
        "submitted_at": plan["signatures"].get(user_id, {}).get("signed_at"),
    }


def _update_plan_status(plan):
    """Recompute plan status based on current signatures and data."""
    both_signed = "user1" in plan["signatures"] and "user2" in plan["signatures"]
    both_data = "user1" in plan["data"] and "user2" in plan["data"]
    if both_signed and both_data:
        plan["status"] = "data_ready"
    elif both_signed:
        plan["status"] = "signed"
    else:
        plan["status"] = "created"


class RunStageRequest(BaseModel):
    stage: Stage


def _stage_indices(plan: dict, stage: str) -> list[int]:
    return [i for i, s in enumerate(plan["steps"]) if s.get("stage") == stage]


def _stage_has_invalid(results: list[dict]) -> bool:
    """A stage 'fails' if any step errored OR any step's trimmed output begins with INVALID."""
    for r in results:
        if r.get("status") != "success":
            return True
        out = str(r.get("result") or "").strip()
        if out.upper().startswith("INVALID"):
            return True
    return False


def _run_stage(plan: dict, stage: str) -> list[dict]:
    """Run only the steps in `stage`, threading through the plan's persistent step_outputs."""
    indices = _stage_indices(plan, stage)
    context = {
        "data1": plan["data"].get("user1", ""),
        "data2": plan["data"].get("user2", ""),
        "scripts": plan["scripts"],
    }
    results = execute_steps(
        steps=plan["steps"],
        indices=indices,
        context=context,
        step_outputs=plan["step_outputs"],
        tinfoil_api_key=plan.get("tinfoil_api_key"),
    )
    plan["stage_results"][stage] = results
    failed = _stage_has_invalid(results)
    plan["stage_status"][stage] = "failed" if failed else "passed"
    # Log to the public ledger — ONLY the stage, which steps failed, and each
    # failing step's title. No data, no prompt output, no raw content.
    if failed:
        failed_step_titles = [
            (plan["steps"][r["step"]].get("title") or f"step {r['step']}")
            for r in results
            if r.get("status") != "success" or str(r.get("result") or "").strip().upper().startswith("INVALID")
        ]
        _append_ledger(plan, {
            "type": "stage_failed",
            "stage": stage,
            "failed_steps": failed_step_titles,
        })
    else:
        _append_ledger(plan, {"type": "stage_passed", "stage": stage})
    return results


def _flatten_results(plan: dict) -> list[dict]:
    """Merge per-stage results back into a single ordered list by step index."""
    by_index: dict[int, dict] = {}
    for stage in STAGES:
        for r in (plan["stage_results"].get(stage) or []):
            by_index[r["step"]] = r
    return [by_index[i] for i in sorted(by_index)]


@app.post("/plan/{plan_id}/run-stage")
def run_stage(plan_id: str, req: RunStageRequest):
    """
    Execute a single stage (input / query / output).

    Gating: 'query' requires 'input' to have passed; 'output' requires 'query'
    to have passed. A stage with no steps is auto-marked as 'passed'.
    """
    plan = plans.get(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    if plan["status"] not in ("data_ready", "running", "completed"):
        raise HTTPException(
            status_code=400,
            detail=f"Both parties must sign and submit data first (current status: {plan['status']})",
        )

    stage = req.stage
    prior = {"query": "input", "output": "query"}.get(stage)
    if prior and plan["stage_status"].get(prior) != "passed":
        raise HTTPException(status_code=409, detail=f"Stage '{prior}' has not passed yet")

    plan["status"] = "running"

    # Auto-pass stages that have no steps, so the three-lane UI still advances.
    if not _stage_indices(plan, stage):
        plan["stage_results"][stage] = []
        plan["stage_status"][stage] = "passed"
    else:
        _run_stage(plan, stage)

    # Reflect overall status.
    if all(plan["stage_status"][s] == "passed" for s in STAGES):
        plan["results"] = _flatten_results(plan)
        plan["status"] = "completed"
    elif any(plan["stage_status"][s] == "failed" for s in STAGES):
        plan["results"] = _flatten_results(plan)
        plan["status"] = "blocked"
    else:
        plan["status"] = "running"

    return {
        "stage": stage,
        "stage_status": plan["stage_status"][stage],
        "overall_status": plan["status"],
        "results": plan["stage_results"][stage],
    }


@app.post("/plan/{plan_id}/reset")
def reset_run(plan_id: str):
    """
    Clear the execution state of a plan without deleting it or losing the
    submitted signatures / data. Intended for the demo webapp's "Re-run"
    button: wipes results, stage_results, stage_status, and the internal
    step_outputs cache so the plan can be executed again from scratch.
    """
    plan = plans.get(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    plan["results"] = None
    plan["stage_results"] = {s: None for s in STAGES}
    plan["stage_status"] = {s: "pending" for s in STAGES}
    plan["step_outputs"] = {}
    # Recompute status from signatures / data (back to data_ready if both
    # submitted, else signed / created).
    _update_plan_status(plan)
    return {"status": plan["status"], "stage_status": plan["stage_status"]}


@app.post("/plan/{plan_id}/run")
def run_plan(plan_id: str):
    """Execute the full plan end-to-end by running each stage in order, stopping on failure."""
    plan = plans.get(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    if plan["status"] not in ("data_ready", "running", "completed"):
        raise HTTPException(
            status_code=400,
            detail=f"Both parties must sign and submit data first (current status: {plan['status']})",
        )

    plan["status"] = "running"
    for stage in STAGES:
        if plan["stage_status"][stage] == "passed":
            continue
        if not _stage_indices(plan, stage):
            plan["stage_results"][stage] = []
            plan["stage_status"][stage] = "passed"
            continue
        _run_stage(plan, stage)
        if plan["stage_status"][stage] == "failed":
            plan["results"] = _flatten_results(plan)
            plan["status"] = "blocked"
            return {"status": "blocked", "failed_stage": stage, "results": plan["results"]}

    plan["results"] = _flatten_results(plan)
    plan["status"] = "completed"
    return {"status": "completed", "results": plan["results"]}


@app.post("/plan/{plan_id}/reset")
def reset_plan_execution(plan_id: str):
    """
    Clear execution state for a single plan so it can be re-run from scratch.
    Signatures, data, and the plan itself are preserved — only stage results,
    stage status, step outputs, and the flattened results are wiped.
    Intended for demo / debugging loops.
    """
    plan = plans.get(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    plan["results"] = None
    plan["stage_results"] = {s: None for s in STAGES}
    plan["stage_status"] = {s: "pending" for s in STAGES}
    plan["step_outputs"] = {}
    _update_plan_status(plan)  # back to data_ready / signed / created

    return {"status": plan["status"], "stage_status": plan["stage_status"]}


@app.get("/plan/{plan_id}/ledger")
def get_ledger(plan_id: str):
    """
    Return the public ledger for a plan. Visible to both parties. Entries are
    append-only and never contain raw query text or uploaded data.
    """
    plan = plans.get(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    return {"ledger": plan.get("ledger", [])}


class AppealRequest(BaseModel):
    user_id: str = Field(description="'user1' or 'user2' — the party filing the appeal")
    public_key: str = Field(min_length=64, max_length=64)
    new_data: str = Field(description="Replacement for this user's previously-submitted data")


def _compare_queries_summary(old: str, new: str, api_key: Optional[str]) -> str:
    """
    One-line LLM comparison of two query submissions — the only content that
    gets written to the public ledger on an accepted appeal. Returns a short
    free-text summary (few words) or a fallback if no API key is available.
    """
    from dsl_executor import DEFAULT_MODEL, TINFOIL_API_KEY
    from tinfoil import TinfoilAI
    effective_key = TINFOIL_API_KEY or (api_key or "")
    if not effective_key:
        return "summary unavailable (no API key configured)"
    prompt = (
        "Compare these two versions of a query submission. In 5–12 words, "
        "summarize how the NEW differs from the OLD — focus on semantic or "
        "scope changes (e.g. \"narrowed to single category\", \"removed "
        "per-user breakdown\", \"added label set\"). Output ONLY the "
        "summary phrase, no prefix, no punctuation beyond what's in the "
        "phrase.\n\nOLD:\n" + old + "\n\nNEW:\n" + new + "\n\nSummary:"
    )
    try:
        client = TinfoilAI(api_key=effective_key)
        resp = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=60,
        )
        msg = resp.choices[0].message
        text = msg.content or getattr(msg, "reasoning_content", None) or ""
        text = text.strip().splitlines()[0].strip() if text.strip() else "change summary unavailable"
        # Hard cap the length so nothing resembling a full query leaks onto the ledger.
        if len(text) > 120:
            text = text[:117] + "…"
        return text
    except Exception:
        return "change summary unavailable"


@app.post("/plan/{plan_id}/appeal")
def file_appeal(plan_id: str, req: AppealRequest):
    """
    Appeal a failed input-stage validation. The user whose query was rejected
    submits a replacement. The new query re-runs the input stage. If it also
    fails, the ledger records an appeal_rejected entry. If it passes, a
    short LLM-generated diff summary is written to the ledger and the plan
    proceeds.

    The old query text is preserved server-side for the comparison step but
    never written to the ledger; only the diff phrase is public.
    """
    plan = plans.get(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    if req.user_id not in ("user1", "user2"):
        raise HTTPException(status_code=400, detail="user_id must be 'user1' or 'user2'")
    if plan.get("stage_status", {}).get("input") != "failed":
        raise HTTPException(status_code=409, detail="Appeal only allowed after input-stage failure")
    expected_pk = plan["user1_public_key"] if req.user_id == "user1" else plan["user2_public_key"]
    if req.public_key.lower() != expected_pk.lower():
        raise HTTPException(status_code=403, detail=f"public_key does not match expected key for {req.user_id}")
    if req.user_id not in plan["data"]:
        raise HTTPException(status_code=400, detail=f"{req.user_id} has no prior submission to appeal")

    old_data = plan["data"][req.user_id]
    if req.new_data == old_data:
        raise HTTPException(status_code=400, detail="new_data is identical to the prior submission")

    # Preserve the old query for the comparison step, swap in the new one,
    # and reset execution state so stages re-run against the new data.
    plan["previous_data"][req.user_id] = old_data
    plan["data"][req.user_id] = req.new_data
    plan["results"] = None
    plan["stage_results"] = {s: None for s in STAGES}
    plan["stage_status"] = {s: "pending" for s in STAGES}
    plan["step_outputs"] = {}
    _update_plan_status(plan)
    _append_ledger(plan, {"type": "appeal_filed", "user_id": req.user_id})

    # Re-run the input stage only. Query / output are left for the normal
    # Run button once the appeal has been accepted.
    if _stage_indices(plan, "input"):
        _run_stage(plan, "input")

    if plan["stage_status"]["input"] == "failed":
        _append_ledger(plan, {
            "type": "appeal_rejected",
            "user_id": req.user_id,
            "reason": "new query still fails the policy check",
        })
        return {"status": "appeal_rejected", "stage_status": plan["stage_status"]}

    # Input passed — run the comparison LLM for the public summary.
    summary = _compare_queries_summary(old_data, req.new_data, plan.get("tinfoil_api_key"))
    _append_ledger(plan, {
        "type": "appeal_accepted",
        "user_id": req.user_id,
        "summary": summary,
    })
    return {
        "status": "appeal_accepted",
        "summary": summary,
        "stage_status": plan["stage_status"],
    }


@app.get("/plan/{plan_id}/results")
def get_results(plan_id: str):
    """
    Per-stage + flattened results. Availability is governed client-side by
    the UI's visibility rules (e.g. query outputs stay hidden until 'output'
    passes); the server returns whatever has been computed so far.
    """
    plan = plans.get(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    return {
        "status": plan["status"],
        "stage_status": plan["stage_status"],
        "stage_results": plan["stage_results"],
        "results": plan.get("results"),
    }


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)
