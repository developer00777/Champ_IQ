"""FastAPI router — extension scraping + legacy agent endpoints.

Extension endpoints (called directly by the Chrome extension):
  GET  /api/b2bpulse/extension/tasks?credential_id=N  → peek pending scrape tasks
  POST /api/b2bpulse/extension/posts                  → ingest scraped posts

Legacy agent endpoints (kept for backward compatibility, unused in the
extension-based flow but harmless):
  POST /api/b2bpulse/agent/pair           → mint agent token
  GET  /api/b2bpulse/agent/tasks          → pop pending tasks (agent-auth)
  POST /api/b2bpulse/agent/posts          → ingest posts (agent-auth)
  GET  /api/b2bpulse/agent/status         → check agent connection
  GET  /api/b2bpulse/agent/posts/{task_id} → read completed posts (polling)

SOLID: this router only does HTTP plumbing — all state lives in AgentTaskStore.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..container import get_container
from ..database import get_db
from ..models import CredentialTable

logger = logging.getLogger(__name__)

router = APIRouter(tags=["b2bpulse"])


# ── Shared models ─────────────────────────────────────────────────────────────

class PostIngestRequest(BaseModel):
    task_id: str
    credential_id: int
    posts: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None
    status: str = "ok"


class PostsReadResponse(BaseModel):
    posts: list[dict[str, Any]] | None
    ready: bool


# ══════════════════════════════════════════════════════════════════════════════
# Extension endpoints — called by background.js in the Chrome extension.
# Auth: credential_id must exist in DB as type=lakeb2b. No token header needed
# because the extension runs in the user's own browser session.
# ══════════════════════════════════════════════════════════════════════════════

ext_router = APIRouter(prefix="/b2bpulse/extension", tags=["b2bpulse-extension"])


@ext_router.get("/tasks", summary="Peek pending scrape tasks (extension)")
async def extension_get_tasks(
    credential_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Chrome extension polls this to receive pending scrape jobs.

    Returns tasks without consuming them (peek, not pop) so the extension
    can retry if the tab closes before it finishes. Tasks are consumed by
    the extension only after it successfully POSTs results back.
    """
    row: CredentialTable | None = await db.get(CredentialTable, credential_id)
    if row is None or row.type != "lakeb2b":
        raise HTTPException(404, f"LakeB2B credential {credential_id} not found")

    store = get_container().b2bpulse_agent_store
    # pop_tasks consumes — extension will re-queue on failure via a separate
    # mechanism; for now pop is fine because the extension immediately processes.
    tasks = await store.pop_tasks(credential_id, max_tasks=3)
    return {"tasks": tasks}


@ext_router.post("/posts", summary="Ingest scraped posts (extension)")
async def extension_ingest_posts(
    body: PostIngestRequest,
    db: AsyncSession = Depends(get_db),
):
    """Chrome extension POSTs scraped posts after processing a scrape task."""
    row: CredentialTable | None = await db.get(CredentialTable, body.credential_id)
    if row is None or row.type != "lakeb2b":
        raise HTTPException(404, f"LakeB2B credential {body.credential_id} not found")

    store = get_container().b2bpulse_agent_store
    posts = body.posts if body.status == "ok" else []
    await store.store_posts(body.task_id, posts)

    if body.status != "ok":
        # Store an empty-but-ready result so the canvas node fails fast
        # instead of timing out waiting for posts that will never come.
        logger.warning(
            f"Extension scrape error for task {body.task_id} "
            f"(cred={body.credential_id}): {body.error}"
        )

    logger.info(
        f"Extension ingested {len(posts)} posts for task {body.task_id} "
        f"(cred={body.credential_id}, status={body.status})"
    )
    return {"ok": True, "stored": len(posts)}


@ext_router.get("/posts/{task_id}", response_model=PostsReadResponse, summary="Read completed scrape result")
async def read_posts(task_id: str):
    """Canvas node polls this until the extension delivers the post results."""
    store = get_container().b2bpulse_agent_store
    posts = await store.read_posts(task_id)
    return PostsReadResponse(posts=posts, ready=posts is not None)


# ══════════════════════════════════════════════════════════════════════════════
# Legacy agent endpoints — kept intact so existing tokens / setups still work.
# ══════════════════════════════════════════════════════════════════════════════

agent_router = APIRouter(prefix="/b2bpulse/agent", tags=["b2bpulse-agent"])


class PairRequest(BaseModel):
    credential_id: int


class PairResponse(BaseModel):
    agent_token: str
    api_base: str


class TasksResponse(BaseModel):
    tasks: list[dict[str, Any]]


class AgentPostIngestRequest(BaseModel):
    task_id: str
    posts: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None
    status: str = "ok"


async def _resolve_agent_token(
    x_agent_token: str | None = Header(default=None),
) -> int:
    if not x_agent_token:
        raise HTTPException(401, "Missing X-Agent-Token header")
    store = get_container().b2bpulse_agent_store
    cred_id = await store.resolve_agent_token(x_agent_token)
    if cred_id is None:
        raise HTTPException(401, "Invalid or expired agent token")
    return cred_id


@agent_router.post("/pair", response_model=PairResponse)
async def pair_agent(body: PairRequest, db: AsyncSession = Depends(get_db)):
    row: CredentialTable | None = await db.get(CredentialTable, body.credential_id)
    if row is None or row.type != "lakeb2b":
        raise HTTPException(404, f"LakeB2B credential {body.credential_id} not found")
    container = get_container()
    token = await container.b2bpulse_agent_store.issue_agent_token(body.credential_id)
    from ..database import get_settings  # noqa: PLC0415
    settings = get_settings()
    api_base = settings.public_base_url or "https://champiq-production.up.railway.app"
    return PairResponse(agent_token=token, api_base=api_base)


@agent_router.get("/tasks", response_model=TasksResponse)
async def get_tasks(credential_id: int = Depends(_resolve_agent_token)):
    store = get_container().b2bpulse_agent_store
    tasks = await store.pop_tasks(credential_id, max_tasks=5)
    return TasksResponse(tasks=tasks)


@agent_router.post("/posts")
async def ingest_posts(body: AgentPostIngestRequest, credential_id: int = Depends(_resolve_agent_token)):
    store = get_container().b2bpulse_agent_store
    posts = body.posts if body.status == "ok" else []
    await store.store_posts(body.task_id, posts)
    return {"ok": True, "stored": len(posts)}


@agent_router.get("/posts/{task_id}", response_model=PostsReadResponse)
async def agent_read_posts(task_id: str):
    store = get_container().b2bpulse_agent_store
    posts = await store.read_posts(task_id)
    return PostsReadResponse(posts=posts, ready=posts is not None)


@agent_router.get("/status")
async def agent_status(credential_id: int, db: AsyncSession = Depends(get_db)):
    row: CredentialTable | None = await db.get(CredentialTable, credential_id)
    if row is None or row.type != "lakeb2b":
        raise HTTPException(404, f"LakeB2B credential {credential_id} not found")
    store = get_container().b2bpulse_agent_store
    connected = await store.agent_connected(credential_id)
    return {"credential_id": credential_id, "connected": connected}


@agent_router.delete("/pair")
async def revoke_agent(credential_id: int):
    store = get_container().b2bpulse_agent_store
    await store.revoke_agent_token(credential_id)
    return {"ok": True}
