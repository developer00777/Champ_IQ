"""Centralized timezone helpers for ChampIQ V2 AI Engine.

All timestamps in the system use UTC. Stored as UTC; the frontend
converts to the user's local timezone via toLocaleString().
"""

from datetime import datetime, timezone


def now_utc() -> datetime:
    """Return the current time as a timezone-aware datetime in UTC."""
    return datetime.now(timezone.utc)


# Backward-compatible alias — callers still using now_ist() get UTC.
# The name is preserved to avoid a mass rename; semantics are now UTC.
now_ist = now_utc
