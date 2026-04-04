"""
Client library for interacting with the auditor-in-a-TEE API.
"""

import hashlib
import json
import httpx


class AuditorClient:
    """Client for the auditor-in-a-TEE API."""

    def __init__(self, api_url: str, timeout: float = 120):
        self.api_url = api_url.rstrip("/")
        self.timeout = timeout

    def health(self) -> dict:
        resp = httpx.get(f"{self.api_url}/health", timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def create_plan(
        self,
        name: str,
        data1_format: str,
        data2_format: str,
        steps: list[dict],
        scripts: dict[str, str] | None = None,
        tinfoil_api_key: str | None = None,
    ) -> dict:
        body = {
            "name": name,
            "data1_format": {"description": data1_format, "schema_hint": "text"},
            "data2_format": {"description": data2_format, "schema_hint": "text"},
            "steps": steps,
            "scripts": scripts,
            "tinfoil_api_key": tinfoil_api_key,
        }
        resp = httpx.post(
            f"{self.api_url}/plan",
            json=body,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def get_plan(self, plan_id: str) -> dict:
        resp = httpx.get(f"{self.api_url}/plan/{plan_id}", timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def sign_plan(self, plan_id: str, user_id: str, public_key: str, signature: str = "") -> dict:
        resp = httpx.post(
            f"{self.api_url}/plan/{plan_id}/sign",
            json={"user_id": user_id, "public_key": public_key, "signature": signature},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def submit_data(self, plan_id: str, user_id: str, data: str, public_key: str) -> dict:
        resp = httpx.post(
            f"{self.api_url}/plan/{plan_id}/data",
            json={"user_id": user_id, "data": data, "public_key": public_key},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def run(self, plan_id: str) -> dict:
        resp = httpx.post(
            f"{self.api_url}/plan/{plan_id}/run",
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def get_results(self, plan_id: str) -> dict:
        resp = httpx.get(
            f"{self.api_url}/plan/{plan_id}/results",
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()
