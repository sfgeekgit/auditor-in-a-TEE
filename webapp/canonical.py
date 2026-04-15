"""
Canonical byte representation of a plan, for hashing and signing.

Both the server (this file) and the CLI (auditor_cli/canonical.py) must
produce byte-identical output for the same plan dict. Any change here must
be mirrored in the CLI and covered by the cross-repo contract test.

Do NOT change the json.dumps kwargs (sort_keys=True, default separators)
without a coordinated update on both sides — it would invalidate every
plan hash and signature already in flight.
"""

import hashlib
import json


SUBMIT_DOMAIN_SEP = b"auditor-submit:v1:"


def canonical_plan_bytes(plan: dict) -> bytes:
    """
    Build the canonical byte representation of a plan. The bytes feed both
    sha256 (for plan_hash) and ed25519.sign (for plan signatures).

    Accepts the dict shape stored server-side in `plans[plan_id]` OR a freshly
    validated CreatePlanRequest dump — the keys below must be present in both.
    """
    payload = {
        "name": plan["name"],
        "user1_public_key": plan["user1_public_key"],
        "user2_public_key": plan["user2_public_key"],
        "data1_format": plan["data1_format"],
        "data2_format": plan["data2_format"],
        "steps": plan["steps"],
        "scripts": plan.get("scripts"),
    }
    return json.dumps(payload, sort_keys=True).encode()


def plan_hash_hex(plan: dict) -> str:
    return hashlib.sha256(canonical_plan_bytes(plan)).hexdigest()


def submit_message(plan_hash_hex_str: str, data: str) -> bytes:
    """
    Bytes signed by a party when submitting their private data.

    Domain-separated from plan signatures so a plan signature can never be
    replayed as a data-submission signature. Hashes the data so the signed
    payload stays small regardless of input size.
    """
    return (
        SUBMIT_DOMAIN_SEP
        + bytes.fromhex(plan_hash_hex_str)
        + hashlib.sha256(data.encode()).digest()
    )
