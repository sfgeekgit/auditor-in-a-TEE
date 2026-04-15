"""
End-to-end flow against the real FastAPI server with REQUIRE_SIGNATURES=true.

Uses starlette TestClient to avoid network. Does not exercise the CLI's argparse
layer — see test_cli_integration.py for that. What's covered here is the
backend's verification logic against signatures produced by the CLI's ed25519
implementation.
"""

import hashlib
import os

import pytest
from fastapi.testclient import TestClient

from auditor_cli.canonical import (
    canonical_plan_bytes,
    plan_hash_hex,
    submit_message,
)
from auditor_cli.keys import generate_keypair
from auditor_cli.plan_file import PlanFile


def _normalize(body: dict) -> dict:
    """Round-trip through PlanFile so we canonicalize over the shape the server stores."""
    return PlanFile.model_validate(body).model_dump()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("REQUIRE_SIGNATURES", "true")
    # Force re-import so the module-level REQUIRE_SIGS flag is re-evaluated.
    import importlib
    import sys

    sys.modules.pop("api_server", None)
    import api_server  # noqa: F401 — from webapp/ via conftest sys.path
    importlib.reload(api_server)

    # Reset the in-memory store between tests.
    api_server.plans.clear()
    with TestClient(api_server.app) as c:
        yield c


def _plan_body(pk1: str, pk2: str) -> dict:
    return {
        "name": "Integration test plan",
        "user1_public_key": pk1,
        "user2_public_key": pk2,
        "data1_format": {"description": "d1", "schema_hint": "text"},
        "data2_format": {"description": "d2", "schema_hint": "text"},
        "steps": [{"type": "run_python", "code": "result = data1 + ' ' + data2"}],
    }


def test_full_flow_succeeds_with_valid_signatures(client):
    kp1 = generate_keypair()
    kp2 = generate_keypair()
    body = _plan_body(kp1.public_key_hex, kp2.public_key_hex)

    r = client.post("/plan", json=body)
    assert r.status_code == 200, r.text
    plan = r.json()
    plan_id = plan["plan_id"]

    # CLI and server must agree on canonical bytes. The body goes through PlanFile
    # in the real CLI flow, so _normalize mirrors that.
    local_hash = plan_hash_hex(_normalize(body))
    assert plan["plan_hash"].lower() == local_hash.lower()

    # Sign.
    view = client.get(f"/plan/{plan_id}").json()
    server_view = {
        "name": view["name"],
        "user1_public_key": view["expected_keys"]["user1"],
        "user2_public_key": view["expected_keys"]["user2"],
        "data1_format": view["data1_format"],
        "data2_format": view["data2_format"],
        "steps": view["steps"],
        "scripts": view.get("scripts"),
    }
    for user, kp in [("user1", kp1), ("user2", kp2)]:
        sig = kp.sign(canonical_plan_bytes(server_view))
        r = client.post(
            f"/plan/{plan_id}/sign",
            json={"user_id": user, "public_key": kp.public_key_hex, "signature": sig},
        )
        assert r.status_code == 200, r.text

    # Submit data.
    for user, kp, data in [("user1", kp1, "alpha"), ("user2", kp2, "beta")]:
        sig = kp.sign(submit_message(view["plan_hash"], data))
        r = client.post(
            f"/plan/{plan_id}/data",
            json={
                "user_id": user,
                "data": data,
                "public_key": kp.public_key_hex,
                "signature": sig,
            },
        )
        assert r.status_code == 200, r.text

    # Run.
    r = client.post(f"/plan/{plan_id}/run")
    assert r.status_code == 200, r.text
    results = r.json()["results"]
    assert results[0]["status"] == "success", results[0]
    assert "alpha beta" in results[0]["result"]


def test_sign_rejected_with_wrong_pubkey(client):
    kp1 = generate_keypair()
    kp2 = generate_keypair()
    wrong = generate_keypair()
    body = _plan_body(kp1.public_key_hex, kp2.public_key_hex)
    plan_id = client.post("/plan", json=body).json()["plan_id"]

    r = client.post(
        f"/plan/{plan_id}/sign",
        json={
            "user_id": "user1",
            "public_key": wrong.public_key_hex,
            "signature": wrong.sign(b"anything"),
        },
    )
    assert r.status_code == 403
    assert "does not match expected key" in r.json()["detail"]


def test_sign_rejected_with_invalid_signature(client):
    kp1 = generate_keypair()
    kp2 = generate_keypair()
    body = _plan_body(kp1.public_key_hex, kp2.public_key_hex)
    plan_id = client.post("/plan", json=body).json()["plan_id"]

    # Sign something other than the canonical plan bytes.
    bogus_sig = kp1.sign(b"not the plan")
    r = client.post(
        f"/plan/{plan_id}/sign",
        json={
            "user_id": "user1",
            "public_key": kp1.public_key_hex,
            "signature": bogus_sig,
        },
    )
    assert r.status_code == 403
    assert "Invalid signature" in r.json()["detail"]


def test_submit_rejected_before_sign(client):
    kp1 = generate_keypair()
    kp2 = generate_keypair()
    body = _plan_body(kp1.public_key_hex, kp2.public_key_hex)
    plan_id = client.post("/plan", json=body).json()["plan_id"]

    r = client.post(
        f"/plan/{plan_id}/data",
        json={
            "user_id": "user1",
            "data": "x",
            "public_key": kp1.public_key_hex,
            "signature": kp1.sign(b"whatever"),
        },
    )
    # Status check comes before the sign-check: plan.status == 'created' trips this 400.
    assert r.status_code == 400


def test_submit_rejected_with_wrong_data_signature(client):
    """Sign data A, submit data B — server must reject."""
    kp1 = generate_keypair()
    kp2 = generate_keypair()
    body = _plan_body(kp1.public_key_hex, kp2.public_key_hex)
    plan_id = client.post("/plan", json=body).json()["plan_id"]
    view = client.get(f"/plan/{plan_id}").json()
    server_view = {
        "name": view["name"],
        "user1_public_key": view["expected_keys"]["user1"],
        "user2_public_key": view["expected_keys"]["user2"],
        "data1_format": view["data1_format"],
        "data2_format": view["data2_format"],
        "steps": view["steps"],
        "scripts": view.get("scripts"),
    }

    for user, kp in [("user1", kp1), ("user2", kp2)]:
        client.post(
            f"/plan/{plan_id}/sign",
            json={
                "user_id": user,
                "public_key": kp.public_key_hex,
                "signature": kp.sign(canonical_plan_bytes(server_view)),
            },
        )

    # Sign data "A" but submit data "B".
    wrong_sig = kp1.sign(submit_message(view["plan_hash"], "A"))
    r = client.post(
        f"/plan/{plan_id}/data",
        json={
            "user_id": "user1",
            "data": "B",
            "public_key": kp1.public_key_hex,
            "signature": wrong_sig,
        },
    )
    assert r.status_code == 403
    assert "data signature" in r.json()["detail"]


def test_plan_hash_stable_across_recompute(fixture_plan_dict):
    """Sanity: canonicalization is deterministic."""
    assert plan_hash_hex(fixture_plan_dict) == plan_hash_hex(fixture_plan_dict)


def test_flag_off_accepts_empty_signature(monkeypatch):
    """REQUIRE_SIGNATURES=false path: the old webapp still works."""
    monkeypatch.setenv("REQUIRE_SIGNATURES", "false")
    import importlib
    import sys

    sys.modules.pop("api_server", None)
    import api_server
    importlib.reload(api_server)
    api_server.plans.clear()

    kp1 = generate_keypair()
    kp2 = generate_keypair()
    body = _plan_body(kp1.public_key_hex, kp2.public_key_hex)

    with TestClient(api_server.app) as c:
        plan_id = c.post("/plan", json=body).json()["plan_id"]
        r = c.post(
            f"/plan/{plan_id}/sign",
            json={
                "user_id": "user1",
                "public_key": kp1.public_key_hex,
                "signature": "",
            },
        )
        assert r.status_code == 200, r.text
