"""Research API routes - trigger Perplexity Sonar research for prospects."""

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from champiq_v2.api.dependencies import verify_internal_secret
from champiq_v2.graph.entities import ProspectState
from champiq_v2.graph.service import get_graph_service

router = APIRouter(prefix="/research", tags=["Research"], dependencies=[Depends(verify_internal_secret)])
logger = logging.getLogger(__name__)


class TriggerResearchRequest(BaseModel):
    prospect_id: str
    company_domain: Optional[str] = None


@router.post("/trigger")
async def trigger_research(request: TriggerResearchRequest):
    """Trigger Perplexity Sonar research for a prospect.

    Runs the research worker in the background and returns immediately.
    The gateway calls this endpoint when a prospect enters RESEARCHING state.
    """
    from champiq_v2.workers.research_worker import ResearchWorker

    graph = await get_graph_service()
    prospect = await graph.get_prospect(request.prospect_id)
    if not prospect:
        raise HTTPException(status_code=404, detail="Prospect not found")

    company_domain = (
        request.company_domain
        or (prospect.email.split("@")[-1] if "@" in prospect.email else None)
    )

    await graph.update_prospect_state(request.prospect_id, ProspectState.RESEARCHING)

    async def _run():
        try:
            worker = ResearchWorker()
            await worker.execute({
                "prospect_id": request.prospect_id,
                "research_type": "full",
                "email": prospect.email,
                "company_domain": company_domain,
            })
            # Move to RESEARCHED so gateway knows research is done
            await graph.update_prospect_state(request.prospect_id, ProspectState.RESEARCHED)
        except Exception as e:
            logger.error("Research failed for %s: %s", request.prospect_id, e)

    asyncio.create_task(_run())

    return {
        "status": "started",
        "prospect_id": request.prospect_id,
        "company_domain": company_domain,
    }
