"""Thin httpx client for the auditor-in-a-TEE FastAPI."""

from __future__ import annotations

import httpx


class APIError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(f"HTTP {status}: {detail}")
        self.status = status
        self.detail = detail


def _raise(resp: httpx.Response) -> dict:
    if resp.is_success:
        return resp.json()
    detail: object
    try:
        detail = resp.json().get("detail", resp.text)
    except Exception:
        detail = resp.text
    if isinstance(detail, list):
        detail = "; ".join(d.get("msg", str(d)) if isinstance(d, dict) else str(d) for d in detail)
    raise APIError(resp.status_code, str(detail))


class Client:
    def __init__(self, base_url: str, timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "Client":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def health(self) -> dict:
        return _raise(self._client.get("/health"))

    def create_plan(self, body: dict) -> dict:
        return _raise(self._client.post("/plan", json=body))

    def get_plan(self, plan_id: str) -> dict:
        return _raise(self._client.get(f"/plan/{plan_id}"))

    def sign(self, plan_id: str, body: dict) -> dict:
        return _raise(self._client.post(f"/plan/{plan_id}/sign", json=body))

    def submit_data(self, plan_id: str, body: dict) -> dict:
        return _raise(self._client.post(f"/plan/{plan_id}/data", json=body))

    def run(self, plan_id: str) -> dict:
        return _raise(self._client.post(f"/plan/{plan_id}/run"))

    def results(self, plan_id: str) -> dict:
        return _raise(self._client.get(f"/plan/{plan_id}/results"))
