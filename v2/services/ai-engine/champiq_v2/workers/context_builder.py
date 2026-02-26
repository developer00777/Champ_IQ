"""Context Builder Worker -- Assembles full prospect context for ElevenLabs agents.

Single Responsibility: gather all prospect context from the knowledge graph
(research data, email history, call summaries, CHAMP scores) and format it
as a text summary suitable for ElevenLabs dynamic_variables.

This is used by the gateway before every voice call to build the context
string that gets passed to the ElevenLabs agent via dynamic_variables.

Also returns structured fields (phone, name, company) needed by the
voice call worker to place the call.
"""

import logging
from typing import Any

from champiq_v2.graph.service import get_graph_service
from champiq_v2.workers.base import (
    BaseWorker,
    PermanentError,
    WorkerType,
    activity_stream,
    ActivityEvent,
)
from champiq_v2.utils.timezone import now_ist

logger = logging.getLogger(__name__)


class ContextBuilder(BaseWorker):
    """Assembles full prospect context for ElevenLabs voice agent calls.

    Uses GraphService.get_context_summary() and get_prospect_context() to
    build a comprehensive text summary of everything known about a prospect.

    Returns both:
    - A formatted text context_summary for ElevenLabs dynamic_variables
    - Structured fields (phone, name, company) for the call worker

    Reuses WorkerType.GRAPH_SYNC since context building is a graph read operation.
    """

    worker_type = WorkerType.GRAPH_SYNC

    async def execute(self, task_data: dict[str, Any]) -> dict[str, Any]:
        """Build context summary for ElevenLabs agent.

        Args:
            task_data: {
                "prospect_id": str,
            }

        Returns:
            {
                "context_summary": str,
                "prospect_name": str,
                "company_name": str,
                "phone": str,
            }
        """
        prospect_id = task_data.get("prospect_id")
        if not prospect_id:
            raise PermanentError("No prospect_id provided")

        await activity_stream.emit(ActivityEvent(
            event_type="context_building",
            worker_type=self.worker_type.value,
            prospect_id=prospect_id,
            data={},
        ))

        graph = await get_graph_service()

        # Get the text summary optimised for ElevenLabs agents
        context_summary = await graph.get_context_summary(prospect_id)

        # Get the full structured context for extracting fields
        prospect_context = await graph.get_prospect_context(prospect_id)

        # Extract structured fields the voice worker needs
        prospect_name = ""
        company_name = ""
        phone = ""

        if prospect_context:
            prospect = prospect_context.prospect
            prospect_name = prospect.name or ""
            phone = prospect.phone or ""

            if prospect_context.company:
                company_name = prospect_context.company.name or ""

            # Enrich the context summary with CHAMP score if available
            if prospect.champ_score and context_summary:
                cs = prospect.champ_score
                champ_line = (
                    f"\nCHAMP SCORE: {cs.composite:.0f}/100 ({cs.tier}) -- "
                    f"Challenges: {cs.challenges}, Authority: {cs.authority}, "
                    f"Money: {cs.money}, Priority: {cs.prioritization}"
                )
                context_summary += champ_line

            # Add interaction count for agent awareness
            if prospect_context.interactions:
                interaction_count = len(prospect_context.interactions)
                context_summary += f"\nTotal prior interactions: {interaction_count}"

        if not context_summary:
            context_summary = (
                f"Prospect ID: {prospect_id}. "
                f"Name: {prospect_name or 'Unknown'}. "
                f"Company: {company_name or 'Unknown'}. "
                f"No additional context available from the knowledge graph."
            )

        await activity_stream.emit(ActivityEvent(
            event_type="context_built",
            worker_type=self.worker_type.value,
            prospect_id=prospect_id,
            data={
                "context_length": len(context_summary),
                "has_phone": bool(phone),
                "has_company": bool(company_name),
            },
        ))

        return {
            "context_summary": context_summary,
            "prospect_name": prospect_name,
            "company_name": company_name,
            "phone": phone,
        }
