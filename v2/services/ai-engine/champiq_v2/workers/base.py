"""Base Worker Infrastructure for ChampIQ V2 AI Engine.

Provides the foundational abstractions for all pipeline workers:
- BaseWorker: abstract base class with execute() contract
- WorkerResult / WorkerStatus: structured result reporting
- WorkerType: enum of all worker types (EMAIL, VOICE, RESEARCH, IMAP, PITCH, SUMMARY)
- WorkerRegistry: central registry for worker lookup
- ActivityStream / ActivityEvent: real-time event streaming to gateway
- GatewayBridge: HTTP bridge for pushing events to the gateway
- RetryableError / PermanentError: error classification for retry logic
"""

import asyncio
import json
import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Optional

import httpx

from champiq_v2.config import get_settings
from champiq_v2.utils.timezone import now_ist

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# JSON encoder that handles common non-serialisable types
# ---------------------------------------------------------------------------

class _SafeEncoder(json.JSONEncoder):
    """JSON encoder that handles datetime, Enum, UUID, and set objects."""

    def default(self, o: Any) -> Any:
        if isinstance(o, datetime):
            return o.isoformat()
        if isinstance(o, Enum):
            return o.value
        if isinstance(o, uuid.UUID):
            return str(o)
        if isinstance(o, set):
            return list(o)
        return super().default(o)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class WorkerStatus(str, Enum):
    """Status of a worker execution."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


class WorkerType(str, Enum):
    """Type of worker in the V2 pipeline."""
    EMAIL = "email"
    VOICE = "voice"
    RESEARCH = "research"
    GRAPH_SYNC = "graph_sync"
    IMAP = "imap"
    PITCH = "pitch"
    SUMMARY = "summary"


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class WorkerResult:
    """Structured result returned by every worker execution."""
    worker_type: WorkerType
    status: WorkerStatus
    data: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return json.loads(json.dumps(asdict(self), cls=_SafeEncoder))


# ---------------------------------------------------------------------------
# Activity events & stream
# ---------------------------------------------------------------------------

@dataclass
class ActivityEvent:
    """A single real-time activity event for the frontend."""
    event_type: str
    worker_type: str
    prospect_id: Optional[str] = None
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: Optional[str] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = now_ist().isoformat()

    def to_dict(self) -> dict[str, Any]:
        return json.loads(json.dumps(asdict(self), cls=_SafeEncoder))


class GatewayBridge:
    """HTTP bridge for pushing activity events to the NestJS gateway."""

    def __init__(self):
        settings = get_settings()
        self.gateway_url = getattr(settings, "gateway_url", "http://localhost:4001")
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    async def push_event(self, event: ActivityEvent) -> None:
        """Push an activity event to the gateway via HTTP POST."""
        try:
            client = await self._get_client()
            await client.post(
                f"{self.gateway_url}/api/v2/internal/activity",
                json=event.to_dict(),
            )
        except Exception as e:
            logger.debug("Failed to push event to gateway: %s", e)

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()


class ActivityStream:
    """Manages a stream of activity events, dispatching them to the gateway."""

    def __init__(self):
        self._bridge = GatewayBridge()
        self._listeners: list[asyncio.Queue] = []

    async def emit(self, event: ActivityEvent) -> None:
        """Emit an event to the gateway and all local listeners."""
        await self._bridge.push_event(event)
        for q in self._listeners:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def subscribe(self) -> asyncio.Queue:
        """Subscribe to the event stream. Returns an asyncio.Queue."""
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._listeners.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        """Unsubscribe from the event stream."""
        if q in self._listeners:
            self._listeners.remove(q)

    async def close(self) -> None:
        await self._bridge.close()


# Module-level singleton
activity_stream = ActivityStream()


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------

class RetryableError(Exception):
    """Raised when a worker encounters a transient error that can be retried."""
    pass


class PermanentError(Exception):
    """Raised when a worker encounters a permanent error that should not be retried."""
    pass


# ---------------------------------------------------------------------------
# BaseWorker
# ---------------------------------------------------------------------------

class BaseWorker(ABC):
    """Abstract base class for all V2 pipeline workers.

    Subclasses must:
    - Set ``worker_type`` class attribute to a ``WorkerType`` value
    - Implement ``execute(task_data)`` returning a dict

    The ``run()`` method wraps ``execute()`` with timing, error handling,
    activity-event emission, and structured result packaging.
    """

    worker_type: WorkerType

    def __init__(self):
        self.settings = get_settings()

    async def emit_progress(self, prospect_id: str, message: str) -> None:
        """Emit a progress event to the activity stream."""
        await activity_stream.emit(ActivityEvent(
            event_type="worker_progress",
            worker_type=self.worker_type.value,
            prospect_id=prospect_id,
            data={"message": message},
        ))

    @abstractmethod
    async def execute(self, task_data: dict[str, Any]) -> dict[str, Any]:
        """Execute the worker's core logic.

        Args:
            task_data: Arbitrary dict with worker-specific parameters.

        Returns:
            A dict with the results of the execution.

        Raises:
            RetryableError: if the failure is transient.
            PermanentError: if the failure is permanent.
        """
        ...

    async def run(self, task_data: dict[str, Any]) -> WorkerResult:
        """Run the worker with timing, error handling, and event emission."""
        prospect_id = task_data.get("prospect_id")
        started_at = now_ist()

        await activity_stream.emit(ActivityEvent(
            event_type="worker_started",
            worker_type=self.worker_type.value,
            prospect_id=prospect_id,
            data={"status": WorkerStatus.RUNNING.value},
        ))

        try:
            data = await self.execute(task_data)
            completed_at = now_ist()
            duration_ms = (completed_at - started_at).total_seconds() * 1000

            result = WorkerResult(
                worker_type=self.worker_type,
                status=WorkerStatus.COMPLETED,
                data=data,
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=duration_ms,
            )

            await activity_stream.emit(ActivityEvent(
                event_type="worker_completed",
                worker_type=self.worker_type.value,
                prospect_id=prospect_id,
                data={"status": WorkerStatus.COMPLETED.value, "duration_ms": duration_ms},
            ))

            return result

        except RetryableError as e:
            logger.warning("Retryable error in %s: %s", self.worker_type.value, e)
            completed_at = now_ist()
            duration_ms = (completed_at - started_at).total_seconds() * 1000

            await activity_stream.emit(ActivityEvent(
                event_type="worker_retrying",
                worker_type=self.worker_type.value,
                prospect_id=prospect_id,
                data={"status": WorkerStatus.RETRYING.value, "error": str(e)},
            ))

            return WorkerResult(
                worker_type=self.worker_type,
                status=WorkerStatus.RETRYING,
                error=str(e),
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=duration_ms,
            )

        except PermanentError as e:
            logger.error("Permanent error in %s: %s", self.worker_type.value, e)
            completed_at = now_ist()
            duration_ms = (completed_at - started_at).total_seconds() * 1000

            await activity_stream.emit(ActivityEvent(
                event_type="worker_failed",
                worker_type=self.worker_type.value,
                prospect_id=prospect_id,
                data={"status": WorkerStatus.FAILED.value, "error": str(e)},
            ))

            return WorkerResult(
                worker_type=self.worker_type,
                status=WorkerStatus.FAILED,
                error=str(e),
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=duration_ms,
            )

        except Exception as e:
            logger.exception("Unexpected error in %s: %s", self.worker_type.value, e)
            completed_at = now_ist()
            duration_ms = (completed_at - started_at).total_seconds() * 1000

            await activity_stream.emit(ActivityEvent(
                event_type="worker_failed",
                worker_type=self.worker_type.value,
                prospect_id=prospect_id,
                data={"status": WorkerStatus.FAILED.value, "error": str(e)},
            ))

            return WorkerResult(
                worker_type=self.worker_type,
                status=WorkerStatus.FAILED,
                error=str(e),
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=duration_ms,
            )


# ---------------------------------------------------------------------------
# Worker registry
# ---------------------------------------------------------------------------

class WorkerRegistry:
    """Central registry for looking up workers by type."""

    _workers: dict[WorkerType, BaseWorker] = {}

    @classmethod
    def register(cls, worker: BaseWorker) -> None:
        """Register a worker instance."""
        cls._workers[worker.worker_type] = worker
        logger.info("Registered worker: %s", worker.worker_type.value)

    @classmethod
    def get(cls, worker_type: WorkerType) -> Optional[BaseWorker]:
        """Get a registered worker by type."""
        return cls._workers.get(worker_type)

    @classmethod
    def get_all(cls) -> dict[WorkerType, BaseWorker]:
        """Get all registered workers."""
        return dict(cls._workers)

    @classmethod
    def clear(cls) -> None:
        """Clear all registered workers (useful for testing)."""
        cls._workers.clear()
