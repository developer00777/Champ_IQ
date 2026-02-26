"""Call API routes - voice calls via ElevenLabs workers."""

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from champiq_v2.api.dependencies import verify_internal_secret

router = APIRouter(prefix="/call", tags=["Call"], dependencies=[Depends(verify_internal_secret)])
logger = logging.getLogger(__name__)


class InitiateCallRequest(BaseModel):
    prospect_id: str
    phone_number: str
    agent_type: str = "qualifier"  # qualifier | sales | nurture | auto
    context_summary: Optional[str] = None
    wait_for_transcript: bool = True


class SummarizeTranscriptRequest(BaseModel):
    prospect_id: str
    transcript: str
    call_type: str = "qualifier"


class BuildContextRequest(BaseModel):
    prospect_id: str


@router.post("/initiate")
async def initiate_call(request: InitiateCallRequest):
    """Place an outbound call via ElevenLabs.

    The agent_type selects which ElevenLabs agent to use:
    - qualifier: Lead qualification call
    - sales: Sales pitch call
    - nurture: Nurturing/relationship call
    - auto: Automatic discovery call (no reply path)
    """
    from champiq_v2.workers.voice_worker import VoiceCallWorker

    worker = VoiceCallWorker()

    try:
        result = await worker.execute({
            "prospect_id": request.prospect_id,
            "phone_number": request.phone_number,
            "agent_type": request.agent_type,
            "context_summary": request.context_summary,
            "wait_for_transcript": request.wait_for_transcript,
        })
        return result
    except Exception as e:
        logger.error("Call initiation failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Call initiation failed: {e}")


@router.post("/summarize")
async def summarize_transcript(request: SummarizeTranscriptRequest):
    """Summarize a call transcript and save to graph."""
    from champiq_v2.workers.summary_worker import SummaryWorker

    worker = SummaryWorker()

    try:
        result = await worker.execute({
            "prospect_id": request.prospect_id,
            "transcript": request.transcript,
            "call_type": request.call_type,
        })
        return result
    except Exception as e:
        logger.error("Transcript summarization failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Summarization failed: {e}")


@router.post("/build-context")
async def build_context(request: BuildContextRequest):
    """Build context summary for ElevenLabs dynamic_variables."""
    from champiq_v2.workers.context_builder import ContextBuilder

    worker = ContextBuilder()

    try:
        result = await worker.execute({
            "prospect_id": request.prospect_id,
        })
        return result
    except Exception as e:
        logger.error("Context build failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Context build failed: {e}")
