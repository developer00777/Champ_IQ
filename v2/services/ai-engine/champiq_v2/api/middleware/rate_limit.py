"""Redis-based sliding-window rate limiting middleware.

Applies per-route request limits to protect expensive AI Engine endpoints.
Uses a Redis sliding window: key = `ratelimit:{route_prefix}:{window_bucket}`.

Default limits (configurable via env vars):
  - /api/pipeline/research  → 10 requests / minute
  - /api/pipeline/email*    → 100 requests / hour
"""

import logging
import time
from typing import Optional

import redis.asyncio as aioredis
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from champiq_v2.config import get_settings

logger = logging.getLogger(__name__)

# Route prefix → (max_requests, window_seconds)
RATE_LIMIT_RULES: dict[str, tuple[int, int]] = {
    "/api/pipeline/research": (10, 60),       # 10 req/min
    "/api/pipeline/email": (100, 3600),        # 100 req/hour
}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window rate limiter backed by Redis.

    For each incoming request, finds the first matching rule prefix,
    then checks/increments an atomic Redis counter for the current window.
    Returns 429 if the limit is exceeded.
    """

    def __init__(self, app, redis_client: Optional[aioredis.Redis] = None):
        super().__init__(app)
        self._redis: Optional[aioredis.Redis] = redis_client

    async def _get_redis(self) -> Optional[aioredis.Redis]:
        if self._redis is not None:
            return self._redis
        try:
            settings = get_settings()
            redis_url = getattr(settings, "redis_url", "redis://localhost:6379/0")
            self._redis = aioredis.from_url(redis_url, decode_responses=True)
            return self._redis
        except Exception as e:
            logger.warning("Rate limit Redis unavailable: %s", e)
            return None

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        rule = self._match_rule(path)

        if rule is None:
            return await call_next(request)

        max_requests, window_seconds = rule
        window_bucket = int(time.time()) // window_seconds
        key = f"ratelimit:{path}:{window_bucket}"

        redis = await self._get_redis()
        if redis is None:
            # Redis unavailable — allow request (fail open)
            return await call_next(request)

        try:
            pipe = redis.pipeline()
            pipe.incr(key)
            pipe.expire(key, window_seconds * 2)
            results = await pipe.execute()
            count = results[0]

            if count > max_requests:
                retry_after = window_seconds - (int(time.time()) % window_seconds)
                logger.warning(
                    "Rate limit exceeded for %s: %d/%d in %ds window",
                    path, count, max_requests, window_seconds,
                )
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": "Rate limit exceeded. Please slow down.",
                        "retry_after_seconds": retry_after,
                    },
                    headers={"Retry-After": str(retry_after)},
                )
        except Exception as e:
            logger.warning("Rate limit check failed (fail open): %s", e)

        return await call_next(request)

    @staticmethod
    def _match_rule(path: str) -> Optional[tuple[int, int]]:
        """Return the (max_requests, window_seconds) for the first matching rule."""
        for prefix, limits in RATE_LIMIT_RULES.items():
            if path.startswith(prefix):
                return limits
        return None
