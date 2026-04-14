"""
FastAPI server for the auditor-in-a-TEE agent.

Two parties with private data agree on a computation plan,
submit their data to the TEE, and receive results.
"""

import os
import uuid
import hashlib
import json
import time
from typing import Optional

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from dsl_executor import execute_plan

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
    constitution: Optional[str] = Field(default=None, description="Constitution rules for run_llm steps. Available as {constitution} in prompt template.")
    model: Optional[str] = Field(default=None, description="Model name for run_llm")
    max_tokens: Optional[int] = Field(default=1000)
    script: Optional[str] = Field(default=None, description="Script name for run_python")
    code: Optional[str] = Field(default=None, description="Inline python code for run_python")
    inputs: Optional[list[str]] = Field(default=None, description="Input variable names for run_python")


class CreatePlanRequest(BaseModel):
    name: str = Field(description="Human-readable plan name")
    user1_public_key: str = Field(description="User 1's public key (hex-encoded)")
    user2_public_key: str = Field(description="User 2's public key (hex-encoded)")
    data1_format: DataFormat = Field(description="Expected format for user 1's data")
    data2_format: DataFormat = Field(description="Expected format for user 2's data")
    steps: list[Step] = Field(description="DSL steps to execute")
    scripts: Optional[dict[str, str]] = Field(default=None, description="Named python scripts (name -> code)")
    tinfoil_api_key: Optional[str] = Field(default=None, description="API key for Tinfoil LLM calls")


class SignRequest(BaseModel):
    user_id: str = Field(description="'user1' or 'user2'")
    public_key: str = Field(description="User's public key (hex-encoded)")
    signature: str = Field(default="", description="Signature over the plan hash (placeholder for now)")


class SubmitDataRequest(BaseModel):
    user_id: str = Field(description="'user1' or 'user2'")
    data: str = Field(description="The private data")
    public_key: str = Field(description="User's public key to verify identity")


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

    expected_keys = {
        "user1": req.user1_public_key,
        "user2": req.user2_public_key,
    }

    # Compute a hash of the plan for signing (includes expected public keys and constitution)
    plan_content = json.dumps({
        "name": req.name,
        "user1_public_key": req.user1_public_key,
        "user2_public_key": req.user2_public_key,
        "data1_format": req.data1_format.model_dump(),
        "data2_format": req.data2_format.model_dump(),
        "steps": [s.model_dump() for s in req.steps],
        "scripts": req.scripts,
    }, sort_keys=True)
    plan_hash = hashlib.sha256(plan_content.encode()).hexdigest()

    plans[plan_id] = {
        "id": plan_id,
        "name": req.name,
        "expected_keys": expected_keys,
        "data1_format": req.data1_format.model_dump(),
        "data2_format": req.data2_format.model_dump(),
        "steps": [s.model_dump() for s in req.steps],
        "scripts": req.scripts or {},
        "tinfoil_api_key": req.tinfoil_api_key,
        "plan_hash": plan_hash,
        "signatures": {},
        "data": {},
        "results": None,
        "status": "created",
        "created_at": time.time(),
    }

    return {
        "plan_id": plan_id,
        "plan_hash": plan_hash,
        "status": "created",
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
        "expected_keys": plan["expected_keys"],
        "data1_format": plan["data1_format"],
        "data2_format": plan["data2_format"],
        "steps": plan["steps"],
        "scripts": plan["scripts"],
        "plan_hash": plan["plan_hash"],
        "status": plan["status"],
        "signatures": {k: {"public_key": v["public_key"][:16] + "..."} for k, v in plan["signatures"].items()},
        "data_submitted": {k: True for k in plan["data"]},
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

    # Verify public key matches the one specified at plan creation
    expected_key = plan["expected_keys"].get(req.user_id)
    if expected_key and req.public_key != expected_key:
        raise HTTPException(status_code=403, detail="Public key does not match the key specified in the plan")

    # Verify Ed25519 signature over the plan hash
    if req.signature:
        try:
            public_bytes = bytes.fromhex(req.public_key)
            public_key = Ed25519PublicKey.from_public_bytes(public_bytes)
            signature_bytes = bytes.fromhex(req.signature)
            public_key.verify(signature_bytes, plan["plan_hash"].encode())
        except Exception as e:
            raise HTTPException(status_code=403, detail=f"Invalid signature: {e}")

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

    # Verify public key matches the one used to sign
    if plan["signatures"][req.user_id]["public_key"] != req.public_key:
        raise HTTPException(status_code=403, detail="Public key does not match the key used to sign the plan")

    plan["data"][req.user_id] = req.data
    _update_plan_status(plan)

    return {
        "status": plan["status"],
        "data_submitted_by": list(plan["data"].keys()),
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
