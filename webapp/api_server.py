"""
FastAPI server for the auditor-in-a-TEE agent.

Two parties with private data agree on a computation plan,
submit their data to the TEE, and receive results.
"""

import os
import uuid
import time
from typing import Optional

import uvicorn
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from canonical import canonical_plan_bytes, plan_hash_hex, submit_message
from dsl_executor import execute_plan


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
    prompt: Optional[str] = Field(default=None, description="Prompt template for run_llm")
    constitution: Optional[str] = Field(default=None, description="Constitution text for run_llm, referenced as {constitution} in the prompt")
    model: Optional[str] = Field(default=None, description="Model name for run_llm")
    max_tokens: Optional[int] = Field(default=1000)
    script: Optional[str] = Field(default=None, description="Script name for run_python")
    code: Optional[str] = Field(default=None, description="Inline python code for run_python")
    inputs: Optional[list[str]] = Field(default=None, description="Input variable names for run_python")


class CreatePlanRequest(BaseModel):
    name: str = Field(description="Human-readable plan name")
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
        "results": None,
        "status": "created",
        "created_at": time.time(),
    }
    plan["plan_hash"] = plan_hash_hex(plan)

    plans[plan_id] = plan

    return {
        "plan_id": plan_id,
        "plan_hash": plan["plan_hash"],
        "status": "created",
    }


@app.delete("/plans")
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
        "data1_format": plan["data1_format"],
        "data2_format": plan["data2_format"],
        "steps": plan["steps"],
        "scripts": plan["scripts"],
        "plan_hash": plan["plan_hash"],
        "status": plan["status"],
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

    plan["signatures"][req.user_id] = {
        "public_key": req.public_key,
        "signature": req.signature,
        "signed_at": time.time(),
    }

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

    plan["data"][req.user_id] = req.data
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


@app.post("/plan/{plan_id}/run")
def run_plan(plan_id: str):
    """Execute the plan. Both parties must have signed and submitted data."""
    plan = plans.get(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    if plan["status"] != "data_ready":
        raise HTTPException(status_code=400, detail=f"Both parties must sign and submit data first (current status: {plan['status']})")

    plan["status"] = "running"

    context = {
        "data1": plan["data"].get("user1", ""),
        "data2": plan["data"].get("user2", ""),
        "scripts": plan["scripts"],
    }

    results = execute_plan(
        steps=plan["steps"],
        context=context,
        tinfoil_api_key=plan.get("tinfoil_api_key"),
    )

    plan["results"] = results
    plan["status"] = "completed"

    return {
        "status": "completed",
        "results": results,
    }


@app.get("/plan/{plan_id}/results")
def get_results(plan_id: str):
    """Get execution results. Available to both parties."""
    plan = plans.get(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    if plan["results"] is None:
        raise HTTPException(status_code=400, detail="Plan has not been executed yet")

    return {
        "status": plan["status"],
        "results": plan["results"],
    }


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)
