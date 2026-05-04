"""RemoteB2BPulseClient — calls b2b-pulse.up.railway.app for everything
except post scraping (which goes through the Chrome extension).

Implements IPageTracker, IEngagementClient, IAuditClient.

Auto-refresh: on 401 the client attempts one token refresh via
POST /api/auth/refresh, updates the credential in Postgres, then retries.
The credential resolver (_save_token) is optional — pass it in from the
executor if you want DB write-back; omit it for stateless calls.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Coroutine

import httpx

from .ports import IAuditClient, IEngagementClient, IPageTracker

logger = logging.getLogger(__name__)

B2B_PULSE_BASE = "https://b2b-pulse.up.railway.app"
_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=5.0)

# Callable signature: (credential_id, new_access_token, new_refresh_token) -> None
TokenSaver = Callable[[int, str, str], Coroutine[Any, Any, None]]


def _auth(credentials: dict[str, Any]) -> dict[str, str]:
    token = credentials.get("access_token") or credentials.get("jwt") or ""
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


async def _refresh(credentials: dict[str, Any]) -> dict[str, Any] | None:
    """Try POST /api/auth/refresh. Returns updated credentials dict or None."""
    refresh_token = credentials.get("refresh_token", "")
    if not refresh_token:
        return None
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{B2B_PULSE_BASE}/api/auth/refresh",
                json={"refresh_token": refresh_token},
            )
        if resp.status_code != 200:
            logger.warning("b2b-pulse token refresh failed: %s", resp.text[:200])
            return None
        data = resp.json()
        return {
            **credentials,
            "access_token": data["access_token"],
            "refresh_token": data.get("refresh_token", refresh_token),
        }
    except Exception as exc:
        logger.warning("b2b-pulse token refresh error: %s", exc)
        return None


async def _call(
    method: str,
    path: str,
    credentials: dict[str, Any],
    token_saver: TokenSaver | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    url = f"{B2B_PULSE_BASE}{path}"

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.request(method, url, headers=_auth(credentials), **kwargs)

    # On 401: refresh once and retry
    if resp.status_code == 401:
        refreshed = await _refresh(credentials)
        if refreshed:
            # Persist new tokens if a saver was provided
            if token_saver:
                cred_id = credentials.get("_credential_id")
                if cred_id:
                    try:
                        await token_saver(
                            int(cred_id),
                            refreshed["access_token"],
                            refreshed.get("refresh_token", ""),
                        )
                    except Exception as exc:
                        logger.warning("Failed to persist refreshed token: %s", exc)
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.request(method, url, headers=_auth(refreshed), **kwargs)

    if resp.status_code >= 400:
        raise RuntimeError(
            f"b2b-pulse {method} {path} → {resp.status_code}: {resp.text[:300]}"
        )
    try:
        return resp.json()
    except ValueError:
        return {"raw": resp.text}


class RemoteB2BPulseClient(IPageTracker, IEngagementClient, IAuditClient):
    """Covers all three remote-API ports with automatic token refresh on 401."""

    def __init__(self, token_saver: TokenSaver | None = None) -> None:
        self._token_saver = token_saver

    def _c(self, method: str, path: str, credentials: dict[str, Any], **kw: Any):
        return _call(method, path, credentials, self._token_saver, **kw)

    # ── IPageTracker ─────────────────────────────────────────────────────────

    async def track_page(self, page_url: str, name: str, credentials: dict[str, Any]) -> dict[str, Any]:
        try:
            return await self._c("POST", "/api/tracked-pages", credentials,
                                 json={"url": page_url, "name": name or ""})
        except RuntimeError as exc:
            # 409 = already tracked — treat as success, fetch the existing page
            if "409" in str(exc):
                pages_resp = await self._c("GET", "/api/tracked-pages", credentials)
                pages = pages_resp if isinstance(pages_resp, list) else []
                existing = next((p for p in pages if page_url in str(p.get("url", ""))), None)
                if existing:
                    return {**existing, "already_tracked": True}
                return {"already_tracked": True, "url": page_url}
            raise

    async def list_tracked_pages(self, credentials: dict[str, Any]) -> dict[str, Any]:
        pages = await self._c("GET", "/api/tracked-pages", credentials)
        return {"pages": pages if isinstance(pages, list) else []}

    async def poll_now(self, page_id: str, credentials: dict[str, Any]) -> dict[str, Any]:
        return await self._c("POST", f"/api/tracked-pages/{page_id}/poll-now", credentials)

    # ── IEngagementClient ────────────────────────────────────────────────────

    async def subscribe_page(
        self,
        page_id: str,
        auto_like: bool,
        auto_comment: bool,
        credentials: dict[str, Any],
    ) -> dict[str, Any]:
        payload = {"auto_like": auto_like, "auto_comment": auto_comment, "polling_mode": "normal"}
        try:
            return await self._c("PUT", f"/api/tracked-pages/{page_id}/subscribe",
                                  credentials, json=payload)
        except RuntimeError:
            return await self._c("POST", f"/api/tracked-pages/{page_id}/subscribe",
                                  credentials, json=payload)

    async def generate_comment(self, post_content: str, credentials: dict[str, Any]) -> dict[str, Any]:
        return await self._c("POST", "/api/automation/generate-comment", credentials,
                             json={"post_content": post_content})

    # ── IAuditClient ─────────────────────────────────────────────────────────

    async def get_recent_activity(self, limit: int, credentials: dict[str, Any]) -> dict[str, Any]:
        return await self._c("GET", f"/api/audit/recent-activity?limit={limit}", credentials)

    async def get_analytics(self, credentials: dict[str, Any]) -> dict[str, Any]:
        return await self._c("GET", "/api/audit/analytics/summary", credentials)
