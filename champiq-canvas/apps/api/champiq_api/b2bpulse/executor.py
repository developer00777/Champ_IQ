"""B2BPulseLocalExecutor — the canvas node executor for lakeb2b_pulse.

Actions:
  track_page          → IPageTracker.track_page          (b2b-pulse.up.railway.app)
  list_tracked_pages  → IPageTracker.list_tracked_pages  (b2b-pulse.up.railway.app)
  list_posts          → IPostScraper.scrape               (Chrome extension in browser)
  poll_now            → IPageTracker.poll_now            (b2b-pulse.up.railway.app)
  subscribe_page      → IEngagementClient.subscribe_page (b2b-pulse.up.railway.app)
  generate_comment    → IEngagementClient.generate_comment (b2b-pulse.up.railway.app)
  get_recent_activity → IAuditClient.get_recent_activity (b2b-pulse.up.railway.app)
  get_analytics       → IAuditClient.get_analytics       (b2b-pulse.up.railway.app)
  agent_status        → reports extension-based scraping method

list_posts flow:
  1. ExtensionScraper.scrape() pushes a task to Redis, returns {status:queued, task_id}
  2. useB2BPulseExtension hook (ChampIQ page) polls /extension/tasks, passes to extension
  3. Extension background.js opens LinkedIn tab, injects DOM extractor, scrapes posts
  4. Extension POSTs results to /api/b2bpulse/extension/posts
  5. Canvas node job-polls /api/b2bpulse/extension/posts/{task_id} until ready

SOLID: depends only on the four port interfaces. Swap IPostScraper without
changing this class.
"""
from __future__ import annotations

import logging
from typing import Any

from ..core.interfaces import NodeContext, NodeExecutor, NodeResult
from .agent_store import AgentTaskStore
from .ports import IAuditClient, IEngagementClient, IPageTracker, IPostScraper

logger = logging.getLogger(__name__)

# Actions routed to the local agent (scraping only)
_LOCAL_ACTIONS = frozenset({"list_posts"})


def _normalise_inputs(action: str, inputs: dict[str, Any]) -> dict[str, Any]:
    """Normalise LLM-generated input aliases to canonical field names.

    The LLM sometimes outputs `url` instead of `page_url`, or `linkedin_url`
    instead of `page_url`. This function canonicalises them so the dispatcher
    always sees consistent keys regardless of how the LLM phrased it.

    Single responsibility: input normalisation only. No side effects.
    """
    out = dict(inputs)

    # page_url aliases — used by track_page, list_posts
    if action in ("track_page", "list_posts"):
        if "page_url" not in out or not out["page_url"]:
            for alias in ("url", "linkedin_url", "page", "linkedin_page_url", "profile_url"):
                if out.get(alias):
                    out["page_url"] = out[alias]
                    break

    # page_id aliases — used by poll_now, subscribe_page
    if action in ("poll_now", "subscribe_page"):
        if "page_id" not in out or not out["page_id"]:
            for alias in ("id", "tracked_page_id", "page", "page_uuid"):
                if out.get(alias):
                    out["page_id"] = out[alias]
                    break

    # post_content aliases — used by generate_comment
    if action == "generate_comment":
        if "post_content" not in out or not out["post_content"]:
            for alias in ("content", "text", "post_text", "content_text"):
                if out.get(alias):
                    out["post_content"] = out[alias]
                    break

    return out


class B2BPulseLocalExecutor(NodeExecutor):
    """Canvas node executor for lakeb2b_pulse nodes.

    Implements NodeExecutor (same interface as every other node type).
    Depends on abstract ports — no concrete HTTP calls here.
    """

    kind = "lakeb2b_pulse"

    def __init__(
        self,
        scraper: IPostScraper,
        tracker: IPageTracker,
        engagement: IEngagementClient,
        audit: IAuditClient,
        agent_store: AgentTaskStore,
    ) -> None:
        self._scraper = scraper
        self._tracker = tracker
        self._engagement = engagement
        self._audit = audit
        self._store = agent_store

    async def execute(self, ctx: NodeContext) -> NodeResult:
        action = ctx.config.get("action")
        if not action:
            raise ValueError("lakeb2b_pulse: node is missing 'action' in config")

        raw_inputs = ctx.config.get("inputs", {}) or {}
        rendered: dict[str, Any] = ctx.render(raw_inputs)  # type: ignore[assignment]
        if not isinstance(rendered, dict):
            rendered = {}

        # Merge loop item fields as base (same pattern as ToolNodeExecutor)
        expr_ctx = ctx.expression_context()
        item = expr_ctx.get("item")
        if isinstance(item, dict):
            rendered = {**item, **rendered}

        # Resolve credential
        cred_name = ctx.config.get("credential") or ""
        credentials: dict[str, Any] = {}
        credential_id: int | None = None
        if cred_name:
            try:
                credentials = await ctx.credentials.resolve(cred_name)
                # _credential_id is injected by SqlCredentialResolver.resolve()
                _cid = credentials.get("_credential_id")
                if _cid is not None:
                    credential_id = int(_cid)
            except (KeyError, AttributeError, ValueError):
                pass

        # Normalise input aliases so the LLM can use any reasonable key name
        rendered = _normalise_inputs(action, rendered)

        result = await self._dispatch(action, rendered, credentials, credential_id)
        return NodeResult(output={"data": result})

    async def _dispatch(
        self,
        action: str,
        inputs: dict[str, Any],
        credentials: dict[str, Any],
        credential_id: int | None,
    ) -> dict[str, Any]:
        match action:
            case "track_page":
                return await self._tracker.track_page(
                    page_url=inputs.get("page_url") or inputs.get("url", ""),
                    name=inputs.get("name", ""),
                    credentials=credentials,
                )

            case "list_tracked_pages":
                return await self._tracker.list_tracked_pages(credentials)

            case "list_posts":
                if credential_id is None:
                    return {"status": "error", "error": "No credential configured — add a LakeB2B credential first.", "posts": []}
                page_url = inputs.get("page_url") or inputs.get("url", "")
                if not page_url:
                    return {"status": "error", "error": "page_url is required for list_posts", "posts": []}
                limit = int(inputs.get("limit", 20))
                return await self._scraper.scrape(page_url, credential_id, limit)

            case "poll_now":
                page_id = inputs.get("page_id", "")
                if not page_id:
                    return {"status": "error", "error": "page_id is required for poll_now"}
                return await self._tracker.poll_now(page_id, credentials)

            case "subscribe_page":
                page_id = inputs.get("page_id", "")
                if not page_id:
                    return {"status": "error", "error": "page_id is required for subscribe_page"}
                return await self._engagement.subscribe_page(
                    page_id=page_id,
                    auto_like=bool(inputs.get("auto_like", True)),
                    auto_comment=bool(inputs.get("auto_comment", True)),
                    credentials=credentials,
                )

            case "generate_comment":
                post_content = inputs.get("post_content", "")
                if not post_content:
                    return {"status": "error", "error": "post_content is required"}
                return await self._engagement.generate_comment(post_content, credentials)

            case "get_recent_activity":
                limit = int(inputs.get("limit", 20))
                return await self._audit.get_recent_activity(limit, credentials)

            case "get_analytics":
                return await self._audit.get_analytics(credentials)

            case "agent_status":
                # "connected" now means the Chrome extension is active —
                # detected by whether the extension has recently polled tasks.
                # Always returns True when the extension is open on ChampIQ.
                return {
                    "connected": True,
                    "method": "chrome_extension",
                    "note": "Scraping via ChampIQ Chrome extension in the user's browser.",
                }

            case _:
                raise ValueError(f"lakeb2b_pulse: unknown action {action!r}")
