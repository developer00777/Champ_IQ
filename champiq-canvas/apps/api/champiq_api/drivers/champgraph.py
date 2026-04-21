"""ChampGraph driver.

Routes through the ChampMail backend at CHAMPGRAPH_BASE_URL/api/v1/graph/*.
Auth: JWT bearer token obtained via /api/v1/auth/login (form-encoded).
Credentials stored in canvas: {"email": "...", "password": "..."} OR
the driver falls back to CHAMPSERVER_EMAIL / CHAMPSERVER_PASSWORD from settings.
"""
from __future__ import annotations

from typing import Any

import httpx

from ..core.interfaces import NodeContext, NodeExecutor, NodeResult
from .base import HttpToolDriver


class ChampGraphDriver(HttpToolDriver):
    tool_id = "champgraph"

    actions: dict[str, dict[str, Any]] = {
        "search":            {"method": "POST", "path": "/api/v1/graph/search",                            "auth": "bearer"},
        "semantic_search":   {"method": "POST", "path": "/api/v1/graph/search",                            "auth": "bearer"},
        "chat":              {"method": "POST", "path": "/api/v1/graph/chat",                              "auth": "bearer"},
        "nl_query":          {"method": "POST", "path": "/api/v1/graph/chat",                              "auth": "bearer"},
        "query":             {"method": "POST", "path": "/api/v1/graph/query",                             "auth": "bearer"},
        "ingest_prospect":   {"method": "POST", "path": "/api/v1/graph/ingest",                             "auth": "bearer"},
        "ingest_company":    {"method": "POST", "path": "/api/v1/graph/ingest",                             "auth": "bearer"},
        "add_relationship":  {"method": "POST", "path": "/api/v1/graph/relationships",                     "auth": "bearer"},
        "get_stats":         {"method": "GET",  "path": "/api/v1/graph/stats",                             "auth": "bearer"},
        "account_briefing":  {"method": "GET",  "path": "/api/v1/graph/accounts/{account_name}/briefing",  "auth": "bearer"},
        "stakeholders":      {"method": "GET",  "path": "/api/v1/graph/accounts/{account_name}/stakeholders", "auth": "bearer"},
        "email_context":     {"method": "GET",  "path": "/api/v1/graph/accounts/{account_name}/email-context", "auth": "bearer"},
        "engagement_gaps":   {"method": "GET",  "path": "/api/v1/graph/accounts/{account_name}/engagement-gaps", "auth": "bearer"},
    }

    async def _get_token(self, credentials: dict[str, Any]) -> str:
        from ..database import get_settings
        s = get_settings()
        email = credentials.get("email") or s.champserver_email
        password = credentials.get("password") or s.champserver_password
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                f"{self._base_url}/api/v1/auth/login",
                data={"username": email, "password": password},
            )
            r.raise_for_status()
            return r.json()["access_token"]

    def _build_headers(self, auth_kind: str, credentials: dict[str, Any]) -> dict[str, str]:
        # Token is injected by invoke_with_auth; this is a sync no-op fallback.
        return {"Content-Type": "application/json"}

    async def invoke(
        self,
        action: str,
        inputs: dict[str, Any],
        credentials: dict[str, Any],
    ) -> dict[str, Any]:
        token = credentials.get("_token") or await self._get_token(credentials)
        credentials = {**credentials, "_token": token}
        spec = self.actions.get(action)
        if spec is None:
            raise KeyError(f"champgraph: unknown action {action!r}")

        import urllib.parse
        method = spec.get("method", "POST").upper()
        path = spec.get("path", "").format(
            **{k: urllib.parse.quote(str(v), safe="") for k, v in inputs.items() if isinstance(v, (str, int))}
        )
        url = f"{self._base_url}{path}"
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}

        json_payload = None
        params = None
        if method in {"GET", "DELETE"}:
            params = {k: v for k, v in inputs.items() if v is not None and not k.startswith("_")}
        else:
            json_payload = {k: v for k, v in inputs.items() if not k.startswith("_")}

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.request(method, url, headers=headers, json=json_payload, params=params)
        if response.status_code >= 400:
            raise RuntimeError(f"champgraph.{action} -> {response.status_code}: {response.text[:500]}")
        try:
            return response.json()
        except ValueError:
            return {"raw": response.text}
