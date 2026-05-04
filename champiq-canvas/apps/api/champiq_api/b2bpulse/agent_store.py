"""AgentTaskStore — Redis-backed task queue for the local b2bpulse-agent.

The local agent (running on the user's machine) polls
GET /api/b2bpulse/agent/tasks?agent_token=<token>
to receive pending scrape jobs, then POSTs results back to
POST /api/b2bpulse/agent/posts

This store manages:
  - Agent pairing tokens (credential_id → agent_token, 30-day rolling TTL)
  - Pending scrape tasks queued by the executor
  - Completed post results held until the node job reads them

Key schema (all prefixed `champiq:b2bpulse:`):
  agent:<credential_id>    → agent_token          (30d TTL, rolling)
  token:<agent_token>      → credential_id        (30d TTL, rolling)
  tasks:<credential_id>    → LIST of JSON task    (consumed by agent)
  posts:<task_id>          → JSON result          (60s TTL, read once by executor)
"""
from __future__ import annotations

import json
import logging
import secrets
from typing import Any

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

_PREFIX = "champiq:b2bpulse:"
_AGENT_TTL = 60 * 60 * 24 * 30   # 30 days
_TASK_TTL  = 60 * 60              # 1 hour — task must be claimed within 1h
_POSTS_TTL = 60 * 60              # 1 hour — posts held for job polling


class AgentTaskStore:
    def __init__(self, redis_url: str) -> None:
        self._url = redis_url

    def _r(self) -> aioredis.Redis:
        return aioredis.from_url(self._url, decode_responses=True)

    # ── Pairing ──────────────────────────────────────────────────────────────

    async def issue_agent_token(self, credential_id: int) -> str:
        """Mint (or reuse existing) agent token for this credential."""
        r = self._r()
        try:
            existing = await r.get(f"{_PREFIX}agent:{credential_id}")
            if existing:
                await r.expire(f"{_PREFIX}agent:{credential_id}", _AGENT_TTL)
                await r.expire(f"{_PREFIX}token:{existing}", _AGENT_TTL)
                return existing
            token = secrets.token_urlsafe(32)
            await r.setex(f"{_PREFIX}agent:{credential_id}", _AGENT_TTL, token)
            await r.setex(f"{_PREFIX}token:{token}", _AGENT_TTL, str(credential_id))
            return token
        finally:
            await r.aclose()

    async def resolve_agent_token(self, agent_token: str) -> int | None:
        """Return credential_id for a valid agent token, or None."""
        r = self._r()
        try:
            val = await r.get(f"{_PREFIX}token:{agent_token}")
            if val is None:
                return None
            # Roll TTL on every use
            await r.expire(f"{_PREFIX}token:{agent_token}", _AGENT_TTL)
            await r.expire(f"{_PREFIX}agent:{val}", _AGENT_TTL)
            return int(val)
        finally:
            await r.aclose()

    async def revoke_agent_token(self, credential_id: int) -> None:
        r = self._r()
        try:
            token = await r.get(f"{_PREFIX}agent:{credential_id}")
            if token:
                await r.delete(f"{_PREFIX}token:{token}")
            await r.delete(f"{_PREFIX}agent:{credential_id}")
        finally:
            await r.aclose()

    # ── Task queue ───────────────────────────────────────────────────────────

    async def push_task(self, credential_id: int, task: dict[str, Any]) -> None:
        """Enqueue a scrape task for the local agent to pick up."""
        r = self._r()
        try:
            key = f"{_PREFIX}tasks:{credential_id}"
            await r.lpush(key, json.dumps(task))
            await r.expire(key, _TASK_TTL)
        finally:
            await r.aclose()

    async def pop_tasks(self, credential_id: int, max_tasks: int = 10) -> list[dict[str, Any]]:
        """Pop up to max_tasks pending tasks for this credential (LIFO, newest first)."""
        r = self._r()
        try:
            key = f"{_PREFIX}tasks:{credential_id}"
            pipe = r.pipeline()
            for _ in range(max_tasks):
                pipe.rpop(key)
            results = await pipe.execute()
            return [json.loads(raw) for raw in results if raw is not None]
        finally:
            await r.aclose()

    # ── Post results ─────────────────────────────────────────────────────────

    async def store_posts(self, task_id: str, posts: list[dict[str, Any]]) -> None:
        """Agent calls this after scraping — stores posts keyed by task_id."""
        r = self._r()
        try:
            await r.setex(
                f"{_PREFIX}posts:{task_id}",
                _POSTS_TTL,
                json.dumps(posts),
            )
        finally:
            await r.aclose()

    async def read_posts(self, task_id: str) -> list[dict[str, Any]] | None:
        """Read (non-destructively) posts for a completed task."""
        r = self._r()
        try:
            raw = await r.get(f"{_PREFIX}posts:{task_id}")
            return json.loads(raw) if raw else None
        finally:
            await r.aclose()

    async def agent_connected(self, credential_id: int) -> bool:
        """True if a live agent token exists for this credential."""
        r = self._r()
        try:
            return await r.exists(f"{_PREFIX}agent:{credential_id}") == 1
        finally:
            await r.aclose()
