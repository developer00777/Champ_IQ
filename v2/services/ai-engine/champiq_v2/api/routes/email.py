"""Email API routes - send outreach emails via SMTP worker."""

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from champiq_v2.api.dependencies import verify_internal_secret

router = APIRouter(prefix="/email", tags=["Email"], dependencies=[Depends(verify_internal_secret)])
logger = logging.getLogger(__name__)


class SendEmailRequest(BaseModel):
    prospect_id: str
    to_email: str
    to_name: Optional[str] = None
    variant: str = "primary"  # primary | secondary | nurture | follow_up
    subject: Optional[str] = None
    body: Optional[str] = None
    campaign_id: Optional[str] = None


class SendFollowUpRequest(BaseModel):
    prospect_id: str
    to_email: str
    to_name: Optional[str] = None
    campaign_id: Optional[str] = None


@router.post("/send")
async def send_email(request: SendEmailRequest):
    """Send an outreach email via the SMTP worker.

    If subject/body are omitted, the LLM generates them from graph context.
    All emails include an availability CTA.
    """
    from champiq_v2.workers.smtp_worker import SMTPEmailWorker

    worker = SMTPEmailWorker()

    try:
        result = await worker.execute({
            "prospect_id": request.prospect_id,
            "to_email": request.to_email,
            "to_name": request.to_name,
            "variant": request.variant,
            "subject": request.subject,
            "body": request.body,
            "campaign_id": request.campaign_id,
        })
        return result
    except Exception as e:
        logger.error("Email send failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Email send failed: {e}")


@router.post("/follow-up")
async def send_follow_up(request: SendFollowUpRequest):
    """Send a follow-up email asking for availability again."""
    from champiq_v2.workers.smtp_worker import SMTPEmailWorker

    worker = SMTPEmailWorker()

    try:
        result = await worker.execute({
            "prospect_id": request.prospect_id,
            "to_email": request.to_email,
            "to_name": request.to_name,
            "variant": "follow_up",
            "campaign_id": request.campaign_id,
        })
        return result
    except Exception as e:
        logger.error("Follow-up email failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Follow-up email failed: {e}")


@router.post("/check-reply")
async def check_reply(prospect_id: str, prospect_email: str):
    """Check IMAP inbox for a reply from a specific prospect."""
    from champiq_v2.workers.imap_worker import IMAPWorker

    worker = IMAPWorker()

    try:
        result = await worker.execute({
            "prospect_id": prospect_id,
            "prospect_email": prospect_email,
        })
        return result
    except Exception as e:
        logger.error("IMAP check failed: %s", e)
        raise HTTPException(status_code=500, detail=f"IMAP check failed: {e}")
