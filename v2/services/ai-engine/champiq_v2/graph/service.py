
"""Knowledge Graph Service - Graphiti wrapper for Neo4j.

This service is the single source of truth for all agents.
All reads and writes to the knowledge graph go through this service.
"""

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Optional

from neo4j import AsyncGraphDatabase, AsyncDriver, AsyncSession
from pydantic import BaseModel


def _neo4j_to_python(data: dict) -> dict:
    """Convert Neo4j-specific types (DateTime, etc.) to Python stdlib types.

    Neo4j returns ``neo4j.time.DateTime`` for temporal properties which
    Pydantic's ``datetime`` validator rejects.  This helper walks a dict
    and converts any ``neo4j.time.DateTime`` -> ``datetime.datetime``.
    """
    try:
        from neo4j.time import DateTime as Neo4jDateTime
    except ImportError:
        return data

    out: dict = {}
    for k, v in data.items():
        if isinstance(v, Neo4jDateTime):
            out[k] = v.to_native()
        elif isinstance(v, dict):
            out[k] = _neo4j_to_python(v)
        else:
            out[k] = v
    return out

from champiq_v2.config import get_settings
from champiq_v2.graph.entities import (
    Campaign,
    CHAMPScore,
    Company,
    Interaction,
    LakeB2BService,
    PainPoint,
    Prospect,
    ProspectState,
    TriggerEvent,
)
from champiq_v2.graph.edges import (
    DecidedAction,
    HasPainPoint,
    InteractedVia,
    PitchedWith,
    SolvedBy,
    TemporalEdge,
    TriggeredBy,
    WorksAt,
)

logger = logging.getLogger(__name__)


class GraphQueryResult(BaseModel):
    """Result from a graph query."""

    records: list[dict[str, Any]]
    summary: Optional[dict[str, Any]] = None


class ProspectContext(BaseModel):
    """Full context for a prospect assembled from the graph."""

    prospect: Prospect
    company: Optional[Company] = None
    pain_points: list[PainPoint] = []
    interactions: list[Interaction] = []
    trigger_events: list[TriggerEvent] = []
    similar_prospects: list[dict] = []
    service_matches: list[dict] = []


class GraphService:
    """Knowledge Graph service wrapping Neo4j/Graphiti.

    This is the core service that all agents use to read from and write to
    the knowledge graph. It implements temporal queries and ensures data

    consistency.
    """

    def __init__(self):
        self.settings = get_settings()
        self._driver: Optional[AsyncDriver] = None

    async def connect(self) -> None:
        """Initialize connection to Neo4j."""
        self._driver = AsyncGraphDatabase.driver(
            self.settings.neo4j_uri,
            auth=(
                self.settings.neo4j_user,
                self.settings.neo4j_password.get_secret_value(),
            ),
        )
        # Verify connectivity
        async with self._driver.session() as session:
            await session.run("RETURN 1")
        logger.info("Connected to Neo4j at %s", self.settings.neo4j_uri)

    async def disconnect(self) -> None:
        """Close connection to Neo4j."""
        if self._driver:
            await self._driver.close()
            self._driver = None
            logger.info("Disconnected from Neo4j")

    @asynccontextmanager
    async def session(self):
        """Get a Neo4j session."""
        if not self._driver:
            await self.connect()
        async with self._driver.session(database=self.settings.neo4j_database) as session:
            yield session

    # ==================== Prospect Operations ====================

    async def create_prospect(self, prospect: Prospect) -> Prospect:
        """Create a new prospect node in the graph."""
        async with self.session() as session:
            query = """
            CREATE (p:Prospect $props)
            RETURN p
            """
            result = await session.run(query, props=prospect.model_dump(mode="json"))
            record = await result.single()
            logger.info("Created prospect: %s", prospect.id)
            return prospect

    async def get_prospect(self, prospect_id: str) -> Optional[Prospect]:
        """Get a prospect by ID."""
        async with self.session() as session:
            query = """
            MATCH (p:Prospect {id: $id})
            RETURN p
            """
            result = await session.run(query, id=prospect_id)
            record = await result.single()
            if record:
                return Prospect(**_neo4j_to_python(dict(record["p"])))
            return None

    async def update_prospect(self, prospect: Prospect) -> Prospect:
        """Update a prospect node."""
        prospect.updated_at = datetime.utcnow()
        async with self.session() as session:
            query = """
            MATCH (p:Prospect {id: $id})
            SET p += $props
            RETURN p
            """
            await session.run(
                query, id=prospect.id, props=prospect.model_dump(mode="json")
            )
            logger.info("Updated prospect: %s", prospect.id)
            return prospect

    async def update_prospect_state(
        self, prospect_id: str, state: ProspectState
    ) -> None:
        """Update just the prospect state."""
        async with self.session() as session:
            query = """
            MATCH (p:Prospect {id: $id})
            SET p.state = $state, p.updated_at = datetime()
            """
            await session.run(query, id=prospect_id, state=state.value)
            logger.info("Updated prospect %s state to %s", prospect_id, state.value)

    async def update_prospect_champ_score(
        self, prospect_id: str, champ_score: CHAMPScore
    ) -> None:
        """Update the CHAMP score for a prospect."""
        async with self.session() as session:
            query = """
            MATCH (p:Prospect {id: $id})
            SET p.champ_score = $score, p.updated_at = datetime()
            """
            await session.run(
                query, id=prospect_id, score=champ_score.model_dump(mode="json")
            )
            logger.info(
                "Updated CHAMP score for prospect %s: tier=%s, composite=%.1f",
                prospect_id,
                champ_score.tier,
                champ_score.composite,
            )

    # ==================== Company Operations ====================

    async def create_company(self, company: Company) -> Company:
        """Create a new company node."""
        async with self.session() as session:
            query = """
            MERGE (c:Company {domain: $domain})
            ON CREATE SET c = $props
            ON MATCH SET c += $props
            RETURN c
            """
            await session.run(
                query, domain=company.domain, props=company.model_dump(mode="json")
            )
            logger.info("Created/updated company: %s", company.name)
            return company

    async def get_company(self, company_id: str) -> Optional[Company]:
        """Get a company by ID."""
        async with self.session() as session:
            query = """
            MATCH (c:Company {id: $id})
            RETURN c
            """
            result = await session.run(query, id=company_id)
            record = await result.single()
            if record:
                return Company(**_neo4j_to_python(dict(record["c"])))
            return None

    async def get_company_by_domain(self, domain: str) -> Optional[Company]:
        """Get a company by domain."""
        async with self.session() as session:
            query = """
            MATCH (c:Company {domain: $domain})
            RETURN c
            """
            result = await session.run(query, domain=domain)
            record = await result.single()
            if record:
                return Company(**_neo4j_to_python(dict(record["c"])))
            return None

    async def list_prospects(self, state: Optional[str] = None) -> list[Prospect]:
        """List all prospects, optionally filtered by state."""
        async with self.session() as session:
            if state:
                query = "MATCH (p:Prospect {state: $state}) RETURN p ORDER BY p.created_at DESC"
                result = await session.run(query, state=state)
            else:
                query = "MATCH (p:Prospect) RETURN p ORDER BY p.created_at DESC"
                result = await session.run(query)
            records = await result.data()
            return [Prospect(**_neo4j_to_python(dict(r["p"]))) for r in records]

    async def upsert_company(self, company: Company) -> Company:
        """Create or update a company node (matched by name)."""
        async with self.session() as session:
            query = """
            MERGE (c:Company {name: $name})
            ON CREATE SET c = $props
            ON MATCH SET c += $props
            RETURN c
            """
            await session.run(
                query, name=company.name, props=company.model_dump(mode="json")
            )
            logger.info("Upserted company: %s", company.name)
            return company

    async def link_prospect_to_company(
        self, prospect_id: str, company_name: str
    ) -> None:
        """Create a WORKS_AT relationship between a prospect and a company (by name)."""
        async with self.session() as session:
            query = """
            MATCH (p:Prospect {id: $prospect_id})
            MATCH (c:Company {name: $company_name})
            MERGE (p)-[:WORKS_AT]->(c)
            """
            await session.run(
                query, prospect_id=prospect_id, company_name=company_name
            )
            logger.info("Linked prospect %s -> company %s", prospect_id, company_name)

    async def enrich_prospect(
        self, prospect_id: str, enrichment: dict[str, Any]
    ) -> None:
        """Update specific fields on a prospect node."""
        async with self.session() as session:
            query = """
            MATCH (p:Prospect {id: $id})
            SET p += $props, p.updated_at = datetime()
            """
            await session.run(query, id=prospect_id, props=enrichment)
            logger.info("Enriched prospect %s: %s", prospect_id, list(enrichment.keys()))

    async def create_pain_point_simple(
        self, prospect_id: str, pain_point: PainPoint
    ) -> None:
        """Create a PainPoint node and link it to a prospect (simplified -- no edge model)."""
        async with self.session() as session:
            query = """
            MATCH (p:Prospect {id: $prospect_id})
            MERGE (pp:PainPoint {id: $pp_id})
            ON CREATE SET pp = $pp_props
            MERGE (p)-[:HAS_PAIN_POINT]->(pp)
            """
            await session.run(
                query,
                prospect_id=prospect_id,
                pp_id=pain_point.id,
                pp_props=pain_point.model_dump(mode="json"),
            )
            logger.info("Created pain point for prospect %s: %s", prospect_id, pain_point.description[:60])

    async def create_trigger_event_simple(
        self, prospect_id: str, event: TriggerEvent
    ) -> None:
        """Create a TriggerEvent node and link it to a prospect's company (simplified)."""
        async with self.session() as session:
            # Try to link via company; if no company, link directly to prospect
            query = """
            MATCH (p:Prospect {id: $prospect_id})
            CREATE (te:TriggerEvent $te_props)
            WITH p, te
            OPTIONAL MATCH (p)-[:WORKS_AT]->(c:Company)
            FOREACH (_ IN CASE WHEN c IS NOT NULL THEN [1] ELSE [] END |
                CREATE (te)-[:TRIGGERED_BY]->(c)
            )
            FOREACH (_ IN CASE WHEN c IS NULL THEN [1] ELSE [] END |
                CREATE (te)-[:TRIGGERED_BY]->(p)
            )
            """
            await session.run(
                query,
                prospect_id=prospect_id,
                te_props=event.model_dump(mode="json"),
            )
            logger.info("Created trigger event for prospect %s: %s", prospect_id, event.type.value)

    # ==================== Relationship Operations ====================

    async def create_works_at(
        self, prospect_id: str, company_id: str, edge: WorksAt
    ) -> None:
        """Create a WORKS_AT relationship between prospect and company."""
        async with self.session() as session:
            query = """
            MATCH (p:Prospect {id: $prospect_id})
            MATCH (c:Company {id: $company_id})
            MERGE (p)-[r:WORKS_AT]->(c)
            SET r = $props
            """
            await session.run(
                query,
                prospect_id=prospect_id,
                company_id=company_id,
                props=edge.model_dump(mode="json"),
            )
            logger.info("Created WORKS_AT: %s -> %s", prospect_id, company_id)

    # Alias: callers use graph.create_pain_point(prospect_id, pp)
    async def create_pain_point(
        self, prospect_id: str, pain_point: PainPoint
    ) -> None:
        """Alias for create_pain_point_simple (2-arg form used by workers)."""
        return await self.create_pain_point_simple(prospect_id, pain_point)

    async def create_has_pain_point(
        self, entity_id: str, entity_type: str, pain_point: PainPoint, edge: HasPainPoint
    ) -> None:
        """Create a HAS_PAIN_POINT relationship (full form with edge model)."""
        async with self.session() as session:
            # First create the pain point node
            pp_query = """
            MERGE (pp:PainPoint {id: $pp_id})
            ON CREATE SET pp = $pp_props
            """
            await session.run(
                pp_query, pp_id=pain_point.id, pp_props=pain_point.model_dump(mode="json")
            )

            # Then create the relationship
            rel_query = f"""
            MATCH (e:{entity_type} {{id: $entity_id}})
            MATCH (pp:PainPoint {{id: $pp_id}})
            MERGE (e)-[r:HAS_PAIN_POINT]->(pp)
            SET r = $edge_props
            """
            await session.run(
                rel_query,
                entity_id=entity_id,
                pp_id=pain_point.id,
                edge_props=edge.model_dump(mode="json"),
            )
            logger.info("Created HAS_PAIN_POINT: %s -> %s", entity_id, pain_point.id)

    async def create_interaction(
        self, prospect_id: str, interaction: Interaction
    ) -> None:
        """Create an interaction node and link to prospect."""
        async with self.session() as session:
            query = """
            MATCH (p:Prospect {id: $prospect_id})
            CREATE (i:Interaction $i_props)
            CREATE (p)-[r:INTERACTED_VIA $r_props]->(i)
            SET p.total_interactions = COALESCE(p.total_interactions, 0) + 1,
                p.last_interaction_at = datetime()
            """
            edge = InteractedVia(
                channel=interaction.channel,
                response_type=interaction.outcome.value,
            )
            await session.run(
                query,
                prospect_id=prospect_id,
                i_props=interaction.model_dump(mode="json"),
                r_props=edge.model_dump(mode="json"),
            )
            logger.info(
                "Created interaction for prospect %s: %s", prospect_id, interaction.type
            )

    # Alias: callers use graph.create_trigger_event(prospect_id, trigger)
    async def create_trigger_event(
        self, prospect_id_or_company_id: str, event: TriggerEvent, edge: Optional[TriggeredBy] = None
    ) -> None:
        """Create a trigger event.

        2-arg form (prospect_id, event) -> delegates to create_trigger_event_simple.
        3-arg form (company_id, event, edge) -> uses explicit edge model.
        """
        if edge is None:
            return await self.create_trigger_event_simple(prospect_id_or_company_id, event)

        async with self.session() as session:
            query = """
            MATCH (c:Company {id: $company_id})
            CREATE (t:TriggerEvent $t_props)
            CREATE (t)-[r:TRIGGERED_BY $r_props]->(c)
            """
            await session.run(
                query,
                company_id=prospect_id_or_company_id,
                t_props=event.model_dump(mode="json"),
                r_props=edge.model_dump(mode="json"),
            )
            logger.info(
                "Created trigger event for company %s: %s",
                prospect_id_or_company_id, event.type,
            )

    # ==================== Context Assembly ====================

    async def get_prospect_context(self, prospect_id: str) -> Optional[ProspectContext]:
        """Assemble full context for a prospect from the graph.

        This is the primary method used by the pipeline to get
        all relevant information about a prospect.
        """
        async with self.session() as session:
            query = """
            MATCH (p:Prospect {id: $id})
            OPTIONAL MATCH (p)-[:WORKS_AT]->(c:Company)
            OPTIONAL MATCH (p)-[:HAS_PAIN_POINT]->(pp:PainPoint)
            OPTIONAL MATCH (p)-[:INTERACTED_VIA]->(i:Interaction)
            OPTIONAL MATCH (te:TriggerEvent)-[:TRIGGERED_BY]->(c)
            RETURN p, c,
                   collect(DISTINCT pp) as pain_points,
                   collect(DISTINCT i) as interactions,
                   collect(DISTINCT te) as trigger_events
            """
            result = await session.run(query, id=prospect_id)
            record = await result.single()

            if not record:
                return None

            prospect = Prospect(**_neo4j_to_python(dict(record["p"])))
            company = Company(**_neo4j_to_python(dict(record["c"]))) if record["c"] else None
            pain_points = [PainPoint(**_neo4j_to_python(dict(pp))) for pp in record["pain_points"]]
            interactions = [Interaction(**_neo4j_to_python(dict(i))) for i in record["interactions"]]
            trigger_events = [TriggerEvent(**_neo4j_to_python(dict(te))) for te in record["trigger_events"]]

            # Get service matches for pain points
            service_matches = await self._get_service_matches(session, pain_points)

            return ProspectContext(
                prospect=prospect,
                company=company,
                pain_points=pain_points,
                interactions=interactions,
                trigger_events=trigger_events,
                service_matches=service_matches,
            )

    async def _get_service_matches(
        self, session: AsyncSession, pain_points: list[PainPoint]
    ) -> list[dict]:
        """Get matching LakeB2B services for pain points."""
        if not pain_points:
            return []

        pp_ids = [pp.id for pp in pain_points]
        query = """
        MATCH (pp:PainPoint)-[r:SOLVED_BY]->(s:LakeB2BService)
        WHERE pp.id IN $pp_ids
        RETURN pp.id as pain_point_id, s, r.fit_score as fit_score, r.expected_roi as expected_roi
        ORDER BY r.fit_score DESC
        """
        result = await session.run(query, pp_ids=pp_ids)
        records = await result.data()

        return [
            {
                "pain_point_id": r["pain_point_id"],
                "service": dict(r["s"]),
                "fit_score": r["fit_score"],
                "expected_roi": r["expected_roi"],
            }
            for r in records
        ]

    # ==================== V2: Save Research Data ====================

    async def save_research_data(
        self,
        prospect_id: str,
        company_research: dict[str, Any],
        prospect_research: dict[str, Any],
        pain_points: list[dict[str, Any]],
        trigger_events: list[dict[str, Any]],
    ) -> None:
        """Persist structured research data into the graph.

        Creates/updates the Company node, links PainPoints and TriggerEvents,
        and stores research metadata on the Prospect node.
        """
        # Upsert company if research returned company info
        company_name = company_research.get("name", "")
        company_domain = company_research.get("domain", "")
        if company_name or company_domain:
            company = Company(
                name=company_name,
                domain=company_domain,
                industry=company_research.get("industry", ""),
                employee_count_range=company_research.get("employee_count_range", ""),
                description=company_research.get("description", ""),
            )
            await self.create_company(company)

            # Link prospect -> company
            if company_domain:
                async with self.session() as session:
                    await session.run(
                        """
                        MATCH (p:Prospect {id: $pid}), (c:Company {domain: $domain})
                        MERGE (p)-[:WORKS_AT]->(c)
                        """,
                        pid=prospect_id,
                        domain=company_domain,
                    )

        # Create pain points
        for pp_data in pain_points:
            try:
                pp = PainPoint(
                    category=pp_data.get("category", "operational_inefficiency"),
                    description=pp_data.get("description", ""),
                    severity=pp_data.get("severity", "medium"),
                    source=pp_data.get("source", "research"),
                )
                await self.create_pain_point(prospect_id, pp)
            except Exception as e:
                logger.debug("Skipping pain point: %s", e)

        # Create trigger events
        for te_data in trigger_events:
            try:
                te = TriggerEvent(
                    type=te_data.get("type", "market_change"),
                    description=te_data.get("description", ""),
                    relevance_score=te_data.get("relevance_score", 0.5),
                    source=te_data.get("source", "research"),
                )
                await self.create_trigger_event(prospect_id, te)
            except Exception as e:
                logger.debug("Skipping trigger event: %s", e)

        # Store research summary on prospect node
        async with self.session() as session:
            await session.run(
                """
                MATCH (p:Prospect {id: $id})
                SET p.research_completed = true,
                    p.research_narrative = $narrative,
                    p.updated_at = datetime()
                """,
                id=prospect_id,
                narrative=prospect_research.get("background", ""),
            )

        logger.info("Research data saved to graph for prospect %s", prospect_id)

    # ==================== V2: Context Summary for ElevenLabs ====================

    async def get_context_summary(self, prospect_id: str) -> str:
        """Build a text summary of all prospect context for ElevenLabs agents."""
        context = await self.get_prospect_context(prospect_id)
        if not context:
            return ""

        parts = []
        p = context.prospect
        parts.append(f"Prospect: {p.name}, {p.title or 'Unknown title'}, {p.email}")

        if context.company:
            c = context.company
            parts.append(f"Company: {c.name}, {c.industry}, {c.employee_count_range or 'unknown size'}")

        if context.pain_points:
            pp_text = "; ".join(f"{pp.category.value}: {pp.description}" for pp in context.pain_points[:5])
            parts.append(f"Pain points: {pp_text}")

        if context.interactions:
            recent = context.interactions[-5:]
            interaction_text = "; ".join(f"{i.type.value}: {i.content_summary[:80]}" for i in recent)
            parts.append(f"Recent interactions: {interaction_text}")

        if context.trigger_events:
            trigger_text = "; ".join(f"{te.type.value}: {te.description[:80]}" for te in context.trigger_events[:3])
            parts.append(f"Trigger events: {trigger_text}")

        return " | ".join(parts)

    # ==================== V2: Save Call Summary ====================

    async def save_call_summary(
        self, prospect_id: str, call_type: str, summary: str, transcript: str = ""
    ) -> None:
        """Save a call summary as an interaction in the graph."""
        from champiq_v2.graph.entities import Interaction, InteractionOutcome, InteractionType
        interaction = Interaction(
            type=InteractionType.CALL_COMPLETED,
            channel="voice",
            outcome=InteractionOutcome.NEUTRAL,
            content_summary=f"[{call_type}] {summary[:200]}",
            transcript_summary=summary,
        )
        await self.create_interaction(prospect_id, interaction)

    # ==================== Query Operations ====================

    async def query(self, cypher: str, params: dict = None) -> GraphQueryResult:
        """Execute a read-only Cypher query."""
        async with self.session() as session:
            result = await session.run(cypher, params or {})
            records = await result.data()
            return GraphQueryResult(records=records)

    async def find_similar_prospects(
        self, prospect_id: str, limit: int = 10
    ) -> list[dict]:
        """Find similar prospects for lookalike targeting."""
        async with self.session() as session:
            query = """
            MATCH (p1:Prospect {id: $id})-[:WORKS_AT]->(c1:Company)
            MATCH (p2:Prospect)-[:WORKS_AT]->(c2:Company)
            WHERE p2.id <> p1.id
              AND c2.industry = c1.industry
              AND p2.state IN ['qualified', 'nurturing', 'pitching']
            WITH p1, p2, c1, c2,
                 CASE WHEN p1.title = p2.title THEN 0.3 ELSE 0 END +
                 CASE WHEN c1.employee_count_range = c2.employee_count_range THEN 0.2 ELSE 0 END +
                 0.5 as similarity_score
            RETURN p2, c2, similarity_score
            ORDER BY similarity_score DESC
            LIMIT $limit
            """
            result = await session.run(query, id=prospect_id, limit=limit)
            records = await result.data()
            return records

    async def get_winning_patterns(
        self, industry: str = None, role: str = None
    ) -> list[dict]:
        """Analyze patterns from qualified leads."""
        async with self.session() as session:
            query = """
            MATCH (p:Prospect {state: 'qualified'})-[:WORKS_AT]->(c:Company)
            OPTIONAL MATCH (p)-[:HAS_PAIN_POINT]->(pp:PainPoint)
            WHERE ($industry IS NULL OR c.industry = $industry)
              AND ($role IS NULL OR p.title CONTAINS $role)
            RETURN c.industry as industry,
                   p.title as title,
                   collect(DISTINCT pp.category) as pain_categories,
                   avg(p.champ_score.composite) as avg_champ_score,
                   count(p) as count
            ORDER BY count DESC
            LIMIT 20
            """
            result = await session.run(query, industry=industry, role=role)
            records = await result.data()
            return records

    # ==================== Batch Operations ====================

    async def bulk_update_prospect_states(
        self, prospect_ids: list[str], state: ProspectState
    ) -> int:
        """Bulk update prospect states."""
        async with self.session() as session:
            query = """
            UNWIND $ids as id
            MATCH (p:Prospect {id: id})
            SET p.state = $state, p.updated_at = datetime()
            RETURN count(p) as updated
            """
            result = await session.run(query, ids=prospect_ids, state=state.value)
            record = await result.single()
            return record["updated"]

    # ==================== Schema Setup ====================

    async def setup_schema(self) -> None:
        """Create indexes and constraints for optimal query performance."""
        async with self.session() as session:
            # Indexes
            indexes = [
                "CREATE INDEX prospect_id IF NOT EXISTS FOR (p:Prospect) ON (p.id)",
                "CREATE INDEX prospect_email IF NOT EXISTS FOR (p:Prospect) ON (p.email)",
                "CREATE INDEX prospect_state IF NOT EXISTS FOR (p:Prospect) ON (p.state)",
                "CREATE INDEX company_id IF NOT EXISTS FOR (c:Company) ON (c.id)",
                "CREATE INDEX company_domain IF NOT EXISTS FOR (c:Company) ON (c.domain)",
                "CREATE INDEX pain_point_id IF NOT EXISTS FOR (pp:PainPoint) ON (pp.id)",
                "CREATE INDEX interaction_id IF NOT EXISTS FOR (i:Interaction) ON (i.id)",
                "CREATE INDEX trigger_event_id IF NOT EXISTS FOR (te:TriggerEvent) ON (te.id)",
            ]

            for idx in indexes:
                try:
                    await session.run(idx)
                except Exception as e:
                    logger.warning("Index creation warning: %s", e)

            logger.info("Graph schema setup complete")


# Singleton instance
_graph_service: Optional[GraphService] = None


async def get_graph_service() -> GraphService:
    """Get the graph service singleton."""
    global _graph_service
    if _graph_service is None:
        _graph_service = GraphService()
        await _graph_service.connect()
    return _graph_service
