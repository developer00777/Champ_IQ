"""Pitch API routes - generate personalised outreach content."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from champiq_v2.agents.pitch.agent import PitchPlan, get_pitch_agent
from champiq_v2.api.dependencies import verify_internal_secret

router = APIRouter(prefix="/pitch", tags=["Pitch"], dependencies=[Depends(verify_internal_secret)])
logger = logging.getLogger(__name__)


class GeneratePitchRequest(BaseModel):
    prospect_id: str
    campaign_context: Optional[str] = None
    tone: str = "consultative"
    generate_emails: bool = True
    generate_call_script: bool = True
    email_variants: list[str] = Field(
        default_factory=lambda: ["primary", "secondary", "nurture"]
    )
    call_type: str = "discovery"
    champ_gaps: list[str] = Field(default_factory=list)
    model_override: Optional[str] = None


class QuickPitchRequest(BaseModel):
    prospect_id: str
    campaign_context: Optional[str] = None


@router.post("/generate")
async def generate_pitch(request: GeneratePitchRequest):
    """Generate a complete pitch package (emails + call script).

    The Pitch Agent reads prospect context from the knowledge graph,
    generates email variants and call scripts, with fallback templates.
    """
    agent = get_pitch_agent()

    plan = PitchPlan(
        prospect_id=request.prospect_id,
        campaign_context=request.campaign_context,
        tone=request.tone,
        generate_emails=request.generate_emails,
        generate_call_script=request.generate_call_script,
        email_variants=request.email_variants,
        call_type=request.call_type,
        champ_gaps=request.champ_gaps,
    )

    try:
        result = await agent.generate(plan)
        return result.to_dict()
    except Exception as e:
        logger.error("Pitch generation failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Pitch generation failed: {e}")


@router.post("/quick")
async def quick_pitch(request: QuickPitchRequest):
    """Quick pitch - all 3 email variants + call script in one call."""
    agent = get_pitch_agent()
    try:
        result = await agent.quick_pitch(
            prospect_id=request.prospect_id,
            campaign_context=request.campaign_context,
        )
        return result.to_dict()
    except Exception as e:
        logger.error("Quick pitch failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Quick pitch failed: {e}")


@router.get("/variants")
async def list_variants():
    """List available pitch variant types."""
    return {
        "email_variants": [
            {"variant": "primary", "name": "Primary Pitch", "description": "Lead with top pain point."},
            {"variant": "secondary", "name": "Secondary Angle", "description": "Alternative perspective."},
            {"variant": "nurture", "name": "Nurture", "description": "Thought leadership, no pitch."},
        ],
        "call_types": [
            {"type": "discovery", "name": "Discovery Call"},
            {"type": "qualification", "name": "Qualification Call"},
            {"type": "follow_up", "name": "Follow-up Call"},
        ],
    }
