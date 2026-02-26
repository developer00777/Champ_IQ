"""Graphiti Service - Semantic knowledge graph layer.

Runs alongside GraphService (raw Neo4j). Handles:
- Episode ingestion (research data, transcripts, interactions)
- Semantic search via embeddinggemma embeddings
- Entity/relationship auto-extraction from unstructured text

Uses the same Neo4j instance as GraphService but creates its own
Graphiti-managed node labels (Entity, Episode, etc.).
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from champiq_v2.config import get_settings

logger = logging.getLogger(__name__)


class GraphitiService:
    """Semantic layer over the knowledge graph using Graphiti Core SDK.

    Coexists with GraphService. Provides:
    - Episode ingestion for unstructured text (research, transcripts, emails)
    - Semantic search across all ingested content
    - Entity/relationship auto-extraction via LLM

    All embeddings are generated via embeddinggemma through Ollama.
    """

    def __init__(self):
        self.settings = get_settings()
        self._graphiti = None
        self._initialized: bool = False

    async def initialize(self) -> None:
        """Initialize Graphiti with LLM client, embedder, and Neo4j connection.

        Called once at application startup from main.py lifespan.
        """
        if self._initialized:
            return

        if not self.settings.graphiti_enabled:
            logger.info("Graphiti is disabled (GRAPHITI_ENABLED=false)")
            return

        from graphiti_core import Graphiti
        from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
        from graphiti_core.llm_client.config import LLMConfig
        from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
        from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient

        settings = self.settings

        # LLM client — use OpenRouter (proven fallback) for entity extraction
        or_key = settings.openrouter_api_key.get_secret_value()
        if or_key:
            llm_config = LLMConfig(
                api_key=or_key,
                model=settings.openrouter_model,
                small_model=settings.openrouter_model,
                base_url="https://openrouter.ai/api/v1",
            )
        else:
            # Fall back to primary LLM (Ollama)
            llm_config = LLMConfig(
                api_key=settings.llm_api_key.get_secret_value() or "ollama",
                model=settings.llm_model,
                small_model=settings.llm_model,
                base_url=settings.llm_base_url,
            )
        llm_client = OpenAIGenericClient(config=llm_config)

        # Cross-encoder/reranker — uses same LLM config (OpenRouter or Ollama)
        cross_encoder = OpenAIRerankerClient(config=llm_config)

        # Embedding client — embeddinggemma via Ollama (NO OpenAI fallback)
        embedder_config = OpenAIEmbedderConfig(
            api_key=settings.embedding_api_key or "ollama",
            embedding_model=settings.embedding_model,
            embedding_dim=settings.embedding_dim,
            base_url=settings.embedding_base_url,
        )
        embedder = OpenAIEmbedder(config=embedder_config)

        # Initialize Graphiti with Neo4j connection
        # All components explicitly configured — no defaults that reach out to OpenAI
        self._graphiti = Graphiti(
            uri=settings.neo4j_uri,
            user=settings.neo4j_user,
            password=settings.neo4j_password.get_secret_value(),
            llm_client=llm_client,
            embedder=embedder,
            cross_encoder=cross_encoder,
            store_raw_episode_content=True,
        )

        # Create Graphiti indices and constraints
        await self._graphiti.build_indices_and_constraints()
        self._initialized = True
        logger.info(
            "GraphitiService initialized: embedding=%s@%s, llm=%s",
            settings.embedding_model,
            settings.embedding_base_url,
            settings.openrouter_model if or_key else settings.llm_model,
        )

    async def close(self) -> None:
        """Graceful shutdown."""
        if self._graphiti:
            await self._graphiti.close()
            self._graphiti = None
            self._initialized = False
            logger.info("GraphitiService closed")

    # ==================== Episode Ingestion ====================

    async def ingest_research(
        self,
        prospect_id: str,
        research_text: str,
        prospect_name: str = "",
        company_name: str = "",
    ) -> None:
        """Ingest research data as a Graphiti episode.

        Called after ResearchWorker completes. Graphiti auto-extracts
        entities and relationships from the text.
        """
        if not self._initialized or not self._graphiti:
            return

        from graphiti_core.nodes import EpisodeType

        episode_name = f"research_{prospect_id}"
        source_desc = f"Research data for {prospect_name} at {company_name}".strip()

        try:
            await self._graphiti.add_episode(
                name=episode_name,
                episode_body=research_text,
                source=EpisodeType.text,
                source_description=source_desc,
                reference_time=datetime.now(timezone.utc),
                group_id=self.settings.graphiti_group_id,
            )
            logger.info("Ingested research episode for prospect %s", prospect_id)
        except Exception as e:
            logger.error("Failed to ingest research episode for %s: %s", prospect_id, e)

    async def ingest_transcript(
        self,
        prospect_id: str,
        transcript: str,
        call_type: str = "discovery",
        prospect_name: str = "",
    ) -> None:
        """Ingest a call transcript as a Graphiti episode."""
        if not self._initialized or not self._graphiti:
            return

        from graphiti_core.nodes import EpisodeType

        episode_name = f"call_{call_type}_{prospect_id}"
        source_desc = f"{call_type.title()} call transcript with {prospect_name}".strip()

        try:
            await self._graphiti.add_episode(
                name=episode_name,
                episode_body=transcript,
                source=EpisodeType.text,
                source_description=source_desc,
                reference_time=datetime.now(timezone.utc),
                group_id=self.settings.graphiti_group_id,
            )
            logger.info("Ingested %s transcript for prospect %s", call_type, prospect_id)
        except Exception as e:
            logger.error("Failed to ingest transcript for %s: %s", prospect_id, e)

    async def ingest_interaction(
        self,
        prospect_id: str,
        interaction_summary: str,
        channel: str = "email",
        prospect_name: str = "",
    ) -> None:
        """Ingest an interaction summary (email reply, meeting notes, etc.)."""
        if not self._initialized or not self._graphiti:
            return

        from graphiti_core.nodes import EpisodeType

        episode_name = f"interaction_{channel}_{prospect_id}"
        source_desc = f"{channel.title()} interaction with {prospect_name}".strip()

        try:
            await self._graphiti.add_episode(
                name=episode_name,
                episode_body=interaction_summary,
                source=EpisodeType.text,
                source_description=source_desc,
                reference_time=datetime.now(timezone.utc),
                group_id=self.settings.graphiti_group_id,
            )
            logger.info("Ingested %s interaction for prospect %s", channel, prospect_id)
        except Exception as e:
            logger.error("Failed to ingest interaction for %s: %s", prospect_id, e)

    # ==================== Semantic Search ====================

    async def semantic_search(
        self,
        query: str,
        num_results: int = 10,
    ) -> list[dict[str, Any]]:
        """Search across all ingested episodes using semantic similarity.

        Returns a list of dicts with entity/edge information from Graphiti.
        """
        if not self._initialized or not self._graphiti:
            return []

        try:
            results = await self._graphiti.search(
                query=query,
                group_ids=[self.settings.graphiti_group_id],
                num_results=num_results,
            )
            return [
                {
                    "uuid": str(getattr(edge, "uuid", "")),
                    "name": getattr(edge, "name", ""),
                    "fact": getattr(edge, "fact", ""),
                    "source_node_name": getattr(edge, "source_node_name", ""),
                    "target_node_name": getattr(edge, "target_node_name", ""),
                    "created_at": str(getattr(edge, "created_at", "")),
                    "episodes": [str(ep) for ep in getattr(edge, "episodes", [])],
                }
                for edge in results
            ]
        except Exception as e:
            logger.warning("Semantic search failed: %s", e)
            return []

    async def find_similar_semantic(
        self,
        description: str,
        num_results: int = 5,
    ) -> list[dict[str, Any]]:
        """Find semantically similar content based on a text description."""
        return await self.semantic_search(
            query=description,
            num_results=num_results,
        )


# Singleton
_graphiti_service: Optional[GraphitiService] = None


async def get_graphiti_service() -> GraphitiService:
    """Get the GraphitiService singleton.

    Does NOT auto-initialize — initialization happens in main.py lifespan.
    """
    global _graphiti_service
    if _graphiti_service is None:
        _graphiti_service = GraphitiService()
    return _graphiti_service
