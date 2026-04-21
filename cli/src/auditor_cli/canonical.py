"""
Vendored from webapp/canonical.py. Must produce byte-identical output.

A contract test (tests/test_canonical_contract.py) imports both this module and
the server's copy and asserts they agree on a fixture plan. If you change one,
change both and run the test.
"""

import hashlib
import json


SUBMIT_DOMAIN_SEP = b"auditor-submit:v1:"


def canonical_plan_bytes(plan: dict) -> bytes:
    payload = {
        "name": plan["name"],
        "summary": plan.get("summary"),
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
    return (
        SUBMIT_DOMAIN_SEP
        + bytes.fromhex(plan_hash_hex_str)
        + hashlib.sha256(data.encode()).digest()
    )
