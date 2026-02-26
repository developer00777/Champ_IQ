"""Pipeline API routes - internal endpoints called by the Gateway pipeline service.

These endpoints are the interface between the NestJS Gateway (which owns the
state machine) and the Python AI Engine (which does the AI/ML work).
The Gateway's BullMQ processors call these endpoints at each pipeline stage.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from champiq_v2.api.dependencies import verify_internal_secret

router = APIRouter(prefix="/pipeline", tags=["Pipeline"], dependencies=[Depends(verify_internal_secret)])
logger = logging.getLogger(__name__)


class PipelineResearchRequest(BaseModel):
    prospect_id: str
    company_domain: Optional[str] = None


class PipelinePitchRequest(BaseModel):
    prospect_id: str
    model_override: Optional[str] = None
    campaign_context: Optional[str] = None


class PipelineEmailRequest(BaseModel):
    prospect_id: str
    to_email: str
    to_name: Optional[str] = None
    variant: str = "primary"
    campaign_id: Optional[str] = None


class PipelineImapCheckRequest(BaseModel):
    prospect_id: str
    prospect_email: str


class PipelineCallRequest(BaseModel):
    prospect_id: str
    phone_number: str
    agent_type: str = "qualifier"
    context_summary: Optional[str] = None


class PipelineSummaryRequest(BaseModel):
    prospect_id: str
    transcript: str
    call_type: str = "qualifier"


@router.post("/research")
async def pipeline_research(request: PipelineResearchRequest):
    """Gateway calls this to run Perplexity Sonar research.

    Synchronous - blocks until research is complete so the gateway
    processor knows when to advance the state machine.
    """
    from champiq_v2.workers.research_worker import ResearchWorker
    from champiq_v2.graph.service import get_graph_service

    graph = await get_graph_service()
    prospect = await graph.get_prospect(request.prospect_id)
    if not prospect:
        raise HTTPException(status_code=404, detail="Prospect not found")

    company_domain = (
        request.company_domain
        or (prospect.email.split("@")[-1] if "@" in prospect.email else None)
    )

    worker = ResearchWorker()
    result = await worker.run({
        "prospect_id": request.prospect_id,
        "research_type": "full",
        "email": prospect.email,
        "company_domain": company_domain,
    })
    return result.to_dict()


@router.post("/pitch")
async def pipeline_pitch(request: PipelinePitchRequest):
    """Gateway calls this to generate pitch content."""
    from champiq_v2.workers.pitch_worker import PitchWorker

    worker = PitchWorker()
    result = await worker.run({
        "prospect_id": request.prospect_id,
        "model_override": request.model_override,
        "campaign_context": request.campaign_context,
    })
    return result.to_dict()


@router.post("/email")
async def pipeline_email(request: PipelineEmailRequest):
    """Gateway calls this to send an email."""
    from champiq_v2.workers.smtp_worker import SMTPEmailWorker

    worker = SMTPEmailWorker()
    result = await worker.run({
        "prospect_id": request.prospect_id,
        "to_email": request.to_email,
        "to_name": request.to_name,
        "variant": request.variant,
        "campaign_id": request.campaign_id,
    })
    return result.to_dict()


@router.post("/imap-check")
async def pipeline_imap_check(request: PipelineImapCheckRequest):
    """Gateway calls this to check for email replies."""
    from champiq_v2.workers.imap_worker import IMAPWorker

    worker = IMAPWorker()
    result = await worker.run({
        "prospect_id": request.prospect_id,
        "prospect_email": request.prospect_email,
    })
    return result.to_dict()


@router.post("/call")
async def pipeline_call(request: PipelineCallRequest):
    """Gateway calls this to initiate an ElevenLabs call."""
    from champiq_v2.workers.voice_worker import VoiceCallWorker

    worker = VoiceCallWorker()
    result = await worker.run({
        "prospect_id": request.prospect_id,
        "phone_number": request.phone_number,
        "agent_type": request.agent_type,
        "context_summary": request.context_summary,
        "wait_for_transcript": True,
    })
    return result.to_dict()


@router.post("/summarize")
async def pipeline_summarize(request: PipelineSummaryRequest):
    """Gateway calls this to summarize a call transcript."""
    from champiq_v2.workers.summary_worker import SummaryWorker

    worker = SummaryWorker()
    result = await worker.run({
        "prospect_id": request.prospect_id,
        "transcript": request.transcript,
        "call_type": request.call_type,
    })
    return result.to_dict()


@router.post("/build-context")
async def pipeline_build_context(prospect_id: str):
    """Gateway calls this to build ElevenLabs context before a call."""
    from champiq_v2.workers.context_builder import ContextBuilder

    worker = ContextBuilder()
    result = await worker.run({"prospect_id": prospect_id})
    return result.to_dict()
