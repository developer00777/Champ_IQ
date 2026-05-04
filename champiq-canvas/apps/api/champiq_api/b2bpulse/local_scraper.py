"""ExtensionScraper — IPostScraper implementation that delegates to the
ChampIQ Chrome extension running in the user's browser.

Flow:
  1. executor calls scrape(page_url, credential_id)
  2. we push a scrape task onto the Redis queue (keyed by credential_id)
  3. the Chrome extension (content.js ↔ background.js) polls
       GET /api/b2bpulse/extension/tasks?credential_id=N
     every 10 s while the ChampIQ tab is open
  4. extension opens a hidden LinkedIn tab, injects the DOM scraper,
     collects posts, closes the tab, then POSTs results to
       POST /api/b2bpulse/extension/posts
  5. backend stores posts keyed by task_id
  6. this scraper polls Redis until the extension delivers (or times out)

No local agent, no Node.js, no terminal — the installed Chrome extension
is the only prerequisite. Zero extra setup for the end user.

SOLID: depends only on IPostScraper + AgentTaskStore port.
Swap the underlying queue/store without touching executor.py.
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any

from .agent_store import AgentTaskStore
from .ports import IPostScraper

# How long to wait for the extension to deliver results.
# The extension needs ~30-40s (tab open + SPA hydration + scroll + scrape).
_POLL_TIMEOUT_SECONDS = 90
_POLL_INTERVAL_SECONDS = 2


class ExtensionScraper(IPostScraper):
    """IPostScraper that queues tasks for the Chrome extension to execute.

    Blocks until the extension delivers results (or times out) so callers
    always get a resolved list of posts rather than a 'queued' placeholder.
    """

    def __init__(self, store: AgentTaskStore) -> None:
        self._store = store

    async def scrape(self, page_url: str, credential_id: int, limit: int = 20) -> dict[str, Any]:
        task_id = f"scrape_{uuid.uuid4().hex[:12]}"

        await self._store.push_task(credential_id, {
            "task_id": task_id,
            "action": "scrape_posts",
            "page_url": page_url,
            "limit": limit,
        })

        # Poll Redis until the extension POSTs its results or we time out.
        # The extension picks up the task on its next 10-second poll cycle,
        # opens a LinkedIn tab, scrapes, and stores results via
        # POST /api/b2bpulse/extension/posts → AgentTaskStore.store_posts().
        elapsed = 0.0
        while elapsed < _POLL_TIMEOUT_SECONDS:
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)
            elapsed += _POLL_INTERVAL_SECONDS

            posts = await self._store.read_posts(task_id)
            if posts is not None:
                sliced = posts[:limit] if limit else posts
                return {
                    "status": "ok",
                    "task_id": task_id,
                    "count": len(sliced),
                    "posts": sliced,
                }

        return {
            "status": "error",
            "task_id": task_id,
            "error": (
                "Extension scrape timed out after 90 seconds. "
                "Make sure the ChampIQ Chrome extension is installed, "
                "you are logged into LinkedIn, and the ChampIQ tab is open."
            ),
            "posts": [],
        }
