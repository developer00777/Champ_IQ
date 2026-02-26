"""Research Worker -- Perplexity Sonar Research + Graphiti Ingestion.

Performs deep research on prospects and their companies using Perplexity
Sonar (routed via OpenRouter), then ingests the structured findings into
the Neo4j knowledge graph via Graphiti for semantic search and context
building.

All LLM calls go through LLMService.research() / research_json() which
use the OpenRouter fallback client with model "perplexity/sonar".
No separate Perplexity API key is needed.

Research stages:
1. Company research (overview, products, news, tech stack)
2. Prospect research (background, role, recent activity)
3. Pain point identification (challenges aligned to our offering)
4. Trigger event detection (funding, hiring, expansion, tech changes)
5. Graphiti ingestion (entities + relationships + embeddings)
6. Narrative building (connecting research to sales angles)
"""

import json
import logging
from typing import Any

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from champiq_v2.utils.json_utils import extract_json_flexible

from champiq_v2.config import get_settings
from champiq_v2.graph.service import get_graph_service
from champiq_v2.graph.graphiti_service import get_graphiti_service
from champiq_v2.llm.service import get_llm_service
from champiq_v2.workers.base import (
    BaseWorker,
    RetryableError,
    PermanentError,
    WorkerType,
    activity_stream,
    ActivityEvent,
)
from champiq_v2.utils.timezone import now_ist

logger = logging.getLogger(__name__)

# Shared system prompt for all research queries
RESEARCH_SYSTEM_PROMPT = (
    "You are a professional profile-building assistant. "
    "When given the name of a person or company, generate a structured, "
    "up-to-date profile using public web sources. "
    "For a company, cover: Overview, Products & Services, Leadership, "
    "Financials, Market & Competitors, and Recent News. "
    "For a person, cover: Overview, Background, Education, Recent Mentions, "
    "and a Myers-Briggs personality assessment based on publicly observable "
    "communication style, decision patterns, and leadership behaviour. "
    "Return valid JSON when asked."
)


class ResearchWorker(BaseWorker):
    """Perplexity Sonar research worker with Graphiti ingestion.

    Researches a prospect's company, role, pain points, and trigger events
    using Perplexity Sonar (via OpenRouter), then ingests all findings into
    the knowledge graph for downstream pitch generation and context building.
    """

    worker_type = WorkerType.RESEARCH

    @retry(
        retry=retry_if_exception_type(RetryableError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    async def execute(self, task_data: dict[str, Any]) -> dict[str, Any]:
        """Execute full research pipeline for a prospect.

        Args:
            task_data: {
                "prospect_id": str,
                "company_domain": str (optional),
                "company_name": str (optional),
                "prospect_name": str (optional),
                "prospect_title": str (optional),
            }

        Returns:
            {
                "company_research": {...},
                "prospect_research": {...},
                "pain_points": [...],
                "trigger_events": [...],
                "narrative": str,
                "graphiti_ingested": bool,
            }
        """
        prospect_id = task_data.get("prospect_id")
        if not prospect_id:
            raise PermanentError("No prospect_id provided")

        company_domain = task_data.get("company_domain", "")
        company_name = task_data.get("company_name", "")
        prospect_name = task_data.get("prospect_name", "")
        prospect_title = task_data.get("prospect_title", "")

        if not company_domain and not company_name:
            raise PermanentError("Either company_domain or company_name is required")

        await activity_stream.emit(ActivityEvent(
            event_type="research_started",
            worker_type=self.worker_type.value,
            prospect_id=prospect_id,
            data={"company": company_name or company_domain},
        ))

        llm = get_llm_service()

        # Stage 1: Company research
        company_research = await self._research_company(
            llm, company_domain, company_name
        )

        await activity_stream.emit(ActivityEvent(
            event_type="research_progress",
            worker_type=self.worker_type.value,
            prospect_id=prospect_id,
            data={"stage": "company_complete"},
        ))

        # Stage 2: Prospect research
        prospect_research = await self._research_prospect(
            llm, prospect_name, prospect_title, company_name or company_domain
        )

        await activity_stream.emit(ActivityEvent(
            event_type="research_progress",
            worker_type=self.worker_type.value,
            prospect_id=prospect_id,
            data={"stage": "prospect_complete"},
        ))

        # Stage 3: Pain points
        pain_points = await self._identify_pain_points(
            llm, company_research, prospect_research, prospect_title
        )

        # Stage 4: Trigger events
        trigger_events = await self._detect_trigger_events(
            llm, company_research, company_name or company_domain
        )

        await activity_stream.emit(ActivityEvent(
            event_type="research_progress",
            worker_type=self.worker_type.value,
            prospect_id=prospect_id,
            data={"stage": "analysis_complete"},
        ))

        # Stage 5: Graphiti ingestion
        graphiti_ingested = await self._ingest_to_graphiti(
            prospect_id=prospect_id,
            company_research=company_research,
            prospect_research=prospect_research,
            pain_points=pain_points,
            trigger_events=trigger_events,
            prospect_name=prospect_name,
            company_name=company_name or company_domain,
        )

        # Stage 6: Save to graph service
        await self._save_to_graph(
            prospect_id=prospect_id,
            company_research=company_research,
            prospect_research=prospect_research,
            pain_points=pain_points,
            trigger_events=trigger_events,
        )

        # Stage 7: Build narrative
        narrative = await self._build_narrative(
            llm=llm,
            company_research=company_research,
            prospect_research=prospect_research,
            pain_points=pain_points,
            trigger_events=trigger_events,
            prospect_name=prospect_name,
            prospect_title=prospect_title,
        )

        await activity_stream.emit(ActivityEvent(
            event_type="research_completed",
            worker_type=self.worker_type.value,
            prospect_id=prospect_id,
            data={
                "pain_points_count": len(pain_points),
                "trigger_events_count": len(trigger_events),
                "graphiti_ingested": graphiti_ingested,
            },
        ))

        return {
            "company_research": company_research,
            "prospect_research": prospect_research,
            "pain_points": pain_points,
            "trigger_events": trigger_events,
            "narrative": narrative,
            "graphiti_ingested": graphiti_ingested,
            "researched_at": now_ist().isoformat(),
        }

    # ------------------------------------------------------------------
    # Research stages (all via LLMService -> OpenRouter -> Perplexity)
    # ------------------------------------------------------------------

    async def _research_company(
        self, llm, company_domain: str, company_name: str
    ) -> dict[str, Any]:
        """Stage 1: Research the company via Perplexity Sonar."""
        identifier = company_name or company_domain
        prompt = f"""Build a structured company profile for "{identifier}" (domain: {company_domain}).

Return a JSON object with the following six sections:
{{
    "overview": {{
        "name": "company name",
        "domain": "company domain",
        "description": "1-2 sentence company description",
        "mission": "mission or tagline if available",
        "founded_year": "year or null",
        "headquarters": "city, country"
    }},
    "products_and_services": {{
        "key_offerings": ["offering 1", "offering 2"],
        "markets_served": ["market 1", "market 2"],
        "target_market": "who they sell to",
        "tech_stack": ["technology 1", "technology 2"]
    }},
    "leadership": {{
        "key_executives": [
            {{"name": "exec name", "title": "exec title", "background": "brief background"}}
        ],
        "founders": [
            {{"name": "founder name", "role": "founder/co-founder"}}
        ]
    }},
    "financials": {{
        "revenue_estimate": "e.g. $10M ARR or null",
        "funding_stage": "e.g. Series B, Public, Bootstrapped",
        "total_funding": "e.g. $25M or null",
        "valuation": "e.g. $200M or null",
        "notable_investors": ["investor 1", "investor 2"],
        "employee_count_range": "e.g. 50-200"
    }},
    "market_and_competitors": {{
        "industry": "primary industry",
        "sub_industry": "sub-industry if applicable",
        "market_position": "leader/challenger/niche player",
        "competitors": ["competitor 1", "competitor 2"],
        "growth_signals": ["signal 1", "signal 2"]
    }},
    "recent_news": {{
        "highlights": ["news item 1", "news item 2"],
        "major_deals": ["deal or partnership 1"],
        "product_launches": ["launch 1"]
    }}
}}"""
        try:
            return await llm.research_json(prompt, system_prompt=RESEARCH_SYSTEM_PROMPT)
        except (ValueError, Exception) as e:
            logger.warning("Company research JSON parse failed: %s", e)
            raw = await llm.research(prompt, system_prompt=RESEARCH_SYSTEM_PROMPT)
            return {"raw_response": raw}

    async def _research_prospect(
        self, llm, prospect_name: str, prospect_title: str, company: str
    ) -> dict[str, Any]:
        """Stage 2: Research the prospect via Perplexity Sonar."""
        if not prospect_name:
            return {"raw_response": "No prospect name provided for research"}

        prompt = f"""Build a structured personal profile for "{prospect_name}", {prospect_title} at {company}.

Return a JSON object with the following five sections:
{{
    "overview": {{
        "name": "{prospect_name}",
        "current_title": "{prospect_title}",
        "current_company": "{company}",
        "decision_making_role": "decision maker/influencer/champion/user"
    }},
    "background": {{
        "professional_summary": "work history and career trajectory summary",
        "expertise_areas": ["area 1", "area 2"],
        "notable_achievements": ["achievement 1", "achievement 2"],
        "likely_priorities": ["priority 1", "priority 2"],
        "previous_companies": ["company 1", "company 2"]
    }},
    "education": {{
        "degrees": [
            {{"degree": "e.g. MBA", "institution": "university name", "year": "graduation year or null"}}
        ]
    }},
    "recent_mentions": {{
        "news_appearances": ["article or mention 1", "mention 2"],
        "public_appearances": ["conference talk, podcast, etc."],
        "linkedin_insights": "any relevant LinkedIn activity, posts, or endorsements",
        "online_presence": "brief summary of public online footprint"
    }},
    "personality": {{
        "mbti_type": "e.g. ENTJ",
        "mbti_description": "1-2 sentence description of this type in a professional context",
        "communication_style": "formal/casual/technical/collaborative",
        "decision_style": "analytical/intuitive/consensus-driven/directive",
        "mbti_rationale": "observable evidence from their public behaviour, writing style, or leadership approach that supports this assessment",
        "sales_approach_tip": "how to tailor outreach and conversations to this personality type"
    }}
}}"""
        try:
            return await llm.research_json(prompt, system_prompt=RESEARCH_SYSTEM_PROMPT)
        except (ValueError, Exception) as e:
            logger.warning("Prospect research JSON parse failed: %s", e)
            raw = await llm.research(prompt, system_prompt=RESEARCH_SYSTEM_PROMPT)
            return {"raw_response": raw}

    async def _identify_pain_points(
        self,
        llm,
        company_research: dict[str, Any],
        prospect_research: dict[str, Any],
        prospect_title: str,
    ) -> list[dict[str, Any]]:
        """Stage 3: Identify pain points based on research."""
        prompt = f"""Based on this research, identify the top pain points for a {prospect_title}.

Company research: {json.dumps(company_research, indent=2)}
Prospect research: {json.dumps(prospect_research, indent=2)}

Return a JSON array of pain points:
[
    {{
        "category": "operational|technical|financial|strategic|growth",
        "description": "description of the pain point",
        "severity": 7,
        "evidence": "what evidence supports this",
        "our_solution_angle": "how our B2B data/outreach solution addresses this"
    }}
]

Return 3-5 pain points, ordered by severity (highest first)."""
        try:
            # research_json returns a dict; pain points might be a top-level array
            # so we use research() + manual parse to handle both dict and array
            raw = await llm.research(prompt, system_prompt=RESEARCH_SYSTEM_PROMPT)
            parsed = self._parse_json_flexible(raw)
            if isinstance(parsed, list):
                pain_points = parsed
            elif isinstance(parsed, dict):
                pain_points = parsed.get("pain_points", parsed.get("raw_response", []))
            else:
                pain_points = []
            # Normalize severity to 1–10 range
            for pp in pain_points:
                if isinstance(pp, dict):
                    pp["severity"] = max(1, min(10, int(pp.get("severity", 5))))
            return pain_points
        except Exception as e:
            logger.warning("Pain point identification failed: %s", e)
            return []

    async def _detect_trigger_events(
        self, llm, company_research: dict[str, Any], company: str
    ) -> list[dict[str, Any]]:
        """Stage 4: Detect trigger events that create buying urgency."""
        prompt = f"""Identify recent trigger events for {company} that might create urgency for B2B data, lead generation, or outreach solutions.

Company research: {json.dumps(company_research, indent=2)}

Return a JSON array of trigger events:
[
    {{
        "type": "funding|hiring|expansion|product_launch|leadership_change|tech_adoption|market_shift",
        "description": "what happened",
        "date_approximate": "when (approximate)",
        "relevance_score": 8,
        "outreach_angle": "how to reference this in outreach"
    }}
]

Return 2-4 trigger events if found. Return an empty array if none found."""
        try:
            raw = await llm.research(prompt, system_prompt=RESEARCH_SYSTEM_PROMPT)
            parsed = self._parse_json_flexible(raw)
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict):
                return parsed.get("trigger_events", parsed.get("raw_response", []))
            return []
        except Exception as e:
            logger.warning("Trigger event detection failed: %s", e)
            return []

    @staticmethod
    def _parse_json_flexible(text: str) -> list | dict:
        """Parse JSON from LLM output, handling arrays, objects, and code fences.

        Delegates to champiq_v2.utils.json_utils.extract_json_flexible.
        """
        return extract_json_flexible(text)

    # ------------------------------------------------------------------
    # Graphiti ingestion
    # ------------------------------------------------------------------

    async def _ingest_to_graphiti(
        self,
        prospect_id: str,
        company_research: dict[str, Any],
        prospect_research: dict[str, Any],
        pain_points: list[dict[str, Any]],
        trigger_events: list[dict[str, Any]],
        prospect_name: str,
        company_name: str,
    ) -> bool:
        """Stage 5: Ingest research findings into Graphiti for semantic search."""
        try:
            graphiti = await get_graphiti_service()
            if not graphiti._initialized:
                logger.info("Graphiti not initialized, skipping ingestion")
                return False

            # Ingest company research (nested profile structure)
            co_overview = company_research.get("overview", company_research)
            co_products = company_research.get("products_and_services", {})
            co_market = company_research.get("market_and_competitors", {})
            company_text = (
                f"Company: {company_name}. "
                f"Industry: {co_market.get('industry', company_research.get('industry', 'unknown'))}. "
                f"Description: {co_overview.get('description', company_research.get('description', ''))}. "
                f"Products: {', '.join(co_products.get('key_offerings', company_research.get('products_services', [])))}. "
                f"Tech stack: {', '.join(co_products.get('tech_stack', company_research.get('tech_stack', [])))}."
            )
            await graphiti.add_episode(
                name=f"company_research_{prospect_id}",
                episode_body=company_text,
                source_description=f"Perplexity Sonar research on {company_name}",
                reference_time=now_ist(),
            )

            # Ingest prospect research (nested profile structure)
            if prospect_name:
                pr_overview = prospect_research.get("overview", prospect_research)
                pr_background = prospect_research.get("background", {})
                pr_personality = prospect_research.get("personality", {})
                prospect_text = (
                    f"Prospect: {prospect_name}. "
                    f"Title: {pr_overview.get('current_title', prospect_research.get('title', ''))}. "
                    f"Background: {pr_background.get('professional_summary', prospect_research.get('background', ''))}. "
                    f"Priorities: {', '.join(pr_background.get('likely_priorities', prospect_research.get('likely_priorities', [])))}. "
                    f"MBTI: {pr_personality.get('mbti_type', '')} - {pr_personality.get('mbti_description', '')}."
                )
                await graphiti.add_episode(
                    name=f"prospect_research_{prospect_id}",
                    episode_body=prospect_text,
                    source_description=f"Perplexity Sonar research on {prospect_name}",
                    reference_time=now_ist(),
                )

            # Ingest pain points
            if pain_points and isinstance(pain_points, list):
                pain_text = "Pain points identified: " + "; ".join(
                    f"[{pp.get('category', 'unknown')}] {pp.get('description', '')}"
                    for pp in pain_points
                    if isinstance(pp, dict)
                )
                await graphiti.add_episode(
                    name=f"pain_points_{prospect_id}",
                    episode_body=pain_text,
                    source_description=f"Pain point analysis for {prospect_name} at {company_name}",
                    reference_time=now_ist(),
                )

            # Ingest trigger events
            if trigger_events and isinstance(trigger_events, list):
                trigger_text = "Trigger events: " + "; ".join(
                    f"[{te.get('type', 'unknown')}] {te.get('description', '')}"
                    for te in trigger_events
                    if isinstance(te, dict)
                )
                await graphiti.add_episode(
                    name=f"trigger_events_{prospect_id}",
                    episode_body=trigger_text,
                    source_description=f"Trigger event detection for {company_name}",
                    reference_time=now_ist(),
                )

            logger.info("Graphiti ingestion complete for prospect %s", prospect_id)
            return True

        except Exception as e:
            logger.error("Graphiti ingestion failed (non-critical): %s", e)
            return False

    # ------------------------------------------------------------------
    # Graph persistence
    # ------------------------------------------------------------------

    async def _save_to_graph(
        self,
        prospect_id: str,
        company_research: dict[str, Any],
        prospect_research: dict[str, Any],
        pain_points: list[dict[str, Any]],
        trigger_events: list[dict[str, Any]],
    ) -> None:
        """Stage 6: Save structured research data to the Neo4j graph."""
        try:
            graph = await get_graph_service()
            await graph.save_research_data(
                prospect_id=prospect_id,
                company_research=company_research,
                prospect_research=prospect_research,
                pain_points=pain_points,
                trigger_events=trigger_events,
            )
        except Exception as e:
            logger.warning("Graph save failed (non-critical): %s", e)

    # ------------------------------------------------------------------
    # Narrative building
    # ------------------------------------------------------------------

    async def _build_narrative(
        self,
        llm,
        company_research: dict[str, Any],
        prospect_research: dict[str, Any],
        pain_points: list[dict[str, Any]],
        trigger_events: list[dict[str, Any]],
        prospect_name: str,
        prospect_title: str,
    ) -> str:
        """Stage 7: Build a sales narrative connecting research to outreach angles."""
        # Extract nested fields from the structured profile format
        co_overview = company_research.get("overview", company_research)
        co_market = company_research.get("market_and_competitors", {})
        pr_background = prospect_research.get("background", {})
        pr_personality = prospect_research.get("personality", {})

        company_display = co_overview.get("name", company_research.get("name", "the company"))
        industry_display = co_market.get("industry", company_research.get("industry", ""))
        background_display = pr_background.get(
            "professional_summary", prospect_research.get("background", "")
        )
        mbti_tip = pr_personality.get("sales_approach_tip", "")

        prompt = f"""Based on the following research, write a concise sales narrative
(2-3 paragraphs) that a sales rep could use to understand why this prospect
is a good fit and how to approach them.

Prospect: {prospect_name}, {prospect_title}
Company: {json.dumps(company_display, default=str)}
Industry: {json.dumps(industry_display, default=str)}
Personality (MBTI): {pr_personality.get('mbti_type', 'unknown')} — {pr_personality.get('mbti_description', '')}
Sales Approach Tip: {mbti_tip}

Pain Points:
{json.dumps(pain_points, indent=2, default=str)}

Trigger Events:
{json.dumps(trigger_events, indent=2, default=str)}

Prospect Background:
{json.dumps(background_display, default=str)}

Write a narrative that:
1. Opens with the most relevant trigger event or company context
2. Connects their pain points to our B2B data and outreach solutions
3. Tailors the approach angle to their MBTI personality type
4. Is professional but conversational in tone"""

        try:
            return await llm.research(prompt, system_prompt=RESEARCH_SYSTEM_PROMPT)
        except Exception as e:
            logger.warning("Narrative building failed: %s", e)
            return (
                f"Research completed for {prospect_name} at "
                f"{co_overview.get('name', company_research.get('name', 'unknown company'))}. "
                f"{len(pain_points)} pain points and "
                f"{len(trigger_events)} trigger events identified."
            )
