"""Prospect API routes - graph CRUD for the V2 pipeline."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr

from champiq_v2.api.dependencies import verify_internal_secret
from champiq_v2.graph.entities import CHAMPScore, Prospect, ProspectState
from champiq_v2.graph.service import get_graph_service, ProspectContext
from champiq_v2.scoring.champ_scorer import get_champ_scorer

router = APIRouter(prefix="/prospects", tags=["Prospects"], dependencies=[Depends(verify_internal_secret)])


class CreateProspectRequest(BaseModel):
    id: Optional[str] = None
    name: str
    email: EmailStr
    title: Optional[str] = None
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    company_domain: Optional[str] = None
    source: Optional[str] = None


class ProspectResponse(BaseModel):
    id: str
    name: str
    email: str
    title: Optional[str]
    state: str
    champ_score: Optional[CHAMPScore]
    information_completeness: float


def _to_response(p: Prospect) -> ProspectResponse:
    return ProspectResponse(
        id=p.id,
        name=p.name,
        email=p.email,
        title=p.title,
        state=p.state.value,
        champ_score=p.champ_score,
        information_completeness=p.information_completeness,
    )


@router.get("", response_model=list[ProspectResponse])
async def list_prospects(state: Optional[str] = None):
    graph = await get_graph_service()
    prospects = await graph.list_prospects(state=state)
    return [_to_response(p) for p in prospects]


@router.post("", response_model=ProspectResponse)
async def create_prospect(request: CreateProspectRequest):
    """Create or upsert a prospect in the knowledge graph.

    If `id` is provided and exists, the existing node is returned.
    This lets the gateway sync PostgreSQL prospects into Neo4j.
    """
    graph = await get_graph_service()

    if request.id:
        existing = await graph.get_prospect(request.id)
        if existing:
            return _to_response(existing)

    kwargs: dict = dict(
        name=request.name,
        email=request.email,
        title=request.title,
        phone=request.phone,
        linkedin_url=request.linkedin_url,
        source=request.source,
        state=ProspectState.NEW,
    )
    if request.id:
        kwargs["id"] = request.id

    prospect = Prospect(**kwargs)
    await graph.create_prospect(prospect)
    return _to_response(prospect)


@router.get("/{prospect_id}", response_model=ProspectResponse)
async def get_prospect(prospect_id: str):
    graph = await get_graph_service()
    prospect = await graph.get_prospect(prospect_id)
    if not prospect:
        raise HTTPException(status_code=404, detail="Prospect not found")
    return _to_response(prospect)


@router.get("/{prospect_id}/context")
async def get_prospect_context(prospect_id: str) -> ProspectContext:
    graph = await get_graph_service()
    context = await graph.get_prospect_context(prospect_id)
    if not context:
        raise HTTPException(status_code=404, detail="Prospect not found")
    return context


@router.get("/{prospect_id}/champ-score")
async def get_champ_score(prospect_id: str) -> CHAMPScore:
    scorer = await get_champ_scorer()
    return await scorer.calculate(prospect_id)


class SyncProspectRequest(BaseModel):
    prospect_id: str
    state: Optional[str] = None
    name: Optional[str] = None
    title: Optional[str] = None
    phone: Optional[str] = None


@router.post("/{prospect_id}/sync")
async def sync_prospect(prospect_id: str, request: SyncProspectRequest):
    """Sync prospect data from gateway PostgreSQL to Neo4j."""
    graph = await get_graph_service()
    prospect = await graph.get_prospect(prospect_id)
    if not prospect:
        raise HTTPException(status_code=404, detail="Prospect not found in graph")

    enrichment = {}
    if request.state:
        await graph.update_prospect_state(prospect_id, ProspectState(request.state))
    if request.name:
        enrichment["name"] = request.name
    if request.title:
        enrichment["title"] = request.title
    if request.phone:
        enrichment["phone"] = request.phone

    if enrichment:
        await graph.enrich_prospect(prospect_id, enrichment)

    return {
        "synced": True,
        "prospect_id": prospect_id,
        "fields_updated": list(enrichment.keys()) + (["state"] if request.state else []),
    }
