"""Shared FastAPI dependencies for route authentication and authorization."""

from fastapi import Header, HTTPException

from champiq_v2.config import get_settings


async def verify_internal_secret(
    x_internal_secret: str = Header(alias="X-Internal-Secret"),
) -> None:
    """Verify the internal secret header matches the configured value.

    This guards all AI Engine routes (except health) so only the Gateway
    can call them. The Gateway sends this header from every BullMQ processor.
    """
    settings = get_settings()
    if not settings.internal_secret:
        raise HTTPException(status_code=500, detail="Internal secret not configured")
    if x_internal_secret != settings.internal_secret:
        raise HTTPException(status_code=401, detail="Invalid internal secret")
