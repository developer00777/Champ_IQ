"""B2B Pulse inline module.

Architecture:
  - Scraping (list_posts) → Chrome extension running in the user's browser.
    The extension polls for tasks, opens a hidden LinkedIn tab, scrapes DOM,
    and POSTs results back. Zero local agent / Node.js required.

  - Engagement scheduling  → b2b-pulse.up.railway.app REST API
  - Audit / analytics      → b2b-pulse.up.railway.app REST API
  - Comment generation     → b2b-pulse.up.railway.app REST API

SOLID layout:
  ports.py         — abstract interfaces (IPostScraper, IEngagementClient, …)
  remote.py        — RemoteB2BPulseClient  (calls b2b-pulse.up.railway.app)
  agent_store.py   — AgentTaskStore        (Redis-backed task queue + result store)
  local_scraper.py — ExtensionScraper      (queues tasks for the Chrome extension)
  executor.py      — B2BPulseLocalExecutor (orchestrates; depends only on ports)
  router.py        — FastAPI router: extension task-poll + post-ingest endpoints
"""
from .executor import B2BPulseLocalExecutor

__all__ = ["B2BPulseLocalExecutor"]
