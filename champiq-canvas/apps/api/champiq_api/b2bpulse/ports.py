"""Abstract ports (interfaces) for B2B Pulse.

All concrete implementations depend on these, not on each other.
The executor depends only on these interfaces — Dependency Inversion.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class IPostScraper(ABC):
    """Fetches posts from a tracked LinkedIn page."""

    @abstractmethod
    async def scrape(self, page_url: str, credential_id: int, limit: int = 20) -> dict[str, Any]:
        """Queue or immediately return posts for `page_url`.

        Returns:
            {
              "status": "queued" | "ok" | "error",
              "posts": [...],          # present when status=ok
              "task_id": "...",        # present when status=queued
              "error": "...",          # present when status=error
            }
        """


class IPageTracker(ABC):
    """Registers a LinkedIn URL with B2B Pulse for polling."""

    @abstractmethod
    async def track_page(self, page_url: str, name: str, credentials: dict[str, Any]) -> dict[str, Any]:
        ...

    @abstractmethod
    async def list_tracked_pages(self, credentials: dict[str, Any]) -> dict[str, Any]:
        ...

    @abstractmethod
    async def poll_now(self, page_id: str, credentials: dict[str, Any]) -> dict[str, Any]:
        ...


class IEngagementClient(ABC):
    """Schedules likes/comments on LinkedIn posts."""

    @abstractmethod
    async def subscribe_page(self, page_id: str, auto_like: bool, auto_comment: bool, credentials: dict[str, Any]) -> dict[str, Any]:
        ...

    @abstractmethod
    async def generate_comment(self, post_content: str, credentials: dict[str, Any]) -> dict[str, Any]:
        ...


class IAuditClient(ABC):
    """Reads engagement audit logs and analytics."""

    @abstractmethod
    async def get_recent_activity(self, limit: int, credentials: dict[str, Any]) -> dict[str, Any]:
        ...

    @abstractmethod
    async def get_analytics(self, credentials: dict[str, Any]) -> dict[str, Any]:
        ...
