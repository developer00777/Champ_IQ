"""Configuration management using Pydantic Settings.

All configuration is loaded from environment variables with sensible defaults
for local development.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "ChampIQ V2 AI Engine"
    app_version: str = "0.1.0"
    debug: bool = False
    environment: Literal["development", "staging", "production"] = "development"

    # API Server
    host: str = "0.0.0.0"
    port: int = 8001
    workers: int = 1

    # Neo4j / Graphiti
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: SecretStr = Field(default=SecretStr("neo4j"))
    neo4j_database: str = "neo4j"

    # PostgreSQL (for interaction logging fallback)
    postgres_url: str = "postgresql://postgres:postgres@localhost:5432/champiq"

    # Redis (for job queue state)
    redis_url: str = "redis://localhost:6379/0"

    # LLM Configuration
    # Defaults to vLLM (MiniMax M2.5) at :8080 for production.
    # Override with LLM_PROVIDER=ollama / LLM_BASE_URL=http://localhost:11434/v1
    # for local development with Ollama.
    llm_provider: Literal["ollama", "vllm", "minimax", "openrouter"] = "vllm"
    llm_base_url: str = "http://localhost:8080/v1"  # vLLM default (MiniMax M2.5)
    llm_model: str = "MiniMaxAI/MiniMax-M1-80k"  # Default model
    llm_api_key: SecretStr = Field(default=SecretStr(""))  # Optional for local
    llm_temperature: float = 0.7
    llm_max_tokens: int = 4096
    llm_timeout: int = 120  # seconds

    # OpenRouter fallback (used when primary LLM is unreachable)
    openrouter_api_key: SecretStr = Field(default=SecretStr(""))
    openrouter_model: str = "minimax/minimax-m2.5"

    # Embedding Configuration (embeddinggemma via Ollama for Graphiti)
    embedding_provider: Literal["ollama", "openai"] = "ollama"
    embedding_base_url: str = "http://localhost:11434/v1"
    embedding_model: str = "embeddinggemma"
    embedding_dim: int = 768
    embedding_api_key: str = ""

    # Graphiti (semantic knowledge graph layer)
    graphiti_enabled: bool = True
    graphiti_group_id: str = "champiq"

    # SMTP Configuration
    smtp_host: str = "localhost"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: SecretStr = Field(default=SecretStr(""))
    smtp_from_email: str = "insights@lakeb2b.com"
    smtp_from_name: str = "LakeB2B Insights"
    smtp_use_tls: bool = True

    # IMAP Configuration (for reading email replies)
    imap_host: str = ""
    imap_port: int = 993
    imap_user: str = ""
    imap_password: SecretStr = Field(default=SecretStr(""))
    imap_use_ssl: bool = True

    # V2: IMAP wait duration before follow-up (configurable from frontend)
    imap_wait_hours: int = 24

    # V2: Frontend-selectable pitch model (empty = use default llm_model)
    pitch_model: str = ""

    # Gateway (NestJS) internal bridge
    gateway_url: str = "http://localhost:4001"
    internal_secret: str = "champiq-v2-internal-secret"

    # Voice Agent API (legacy Railway middleware)
    voice_agent_base_url: str = "https://voice-qualified-template-production.up.railway.app"
    voice_agent_api_key: SecretStr = Field(default=SecretStr(""))
    voice_agent_callback_url: str = "http://localhost:8001/webhooks/voice/complete"

    # ElevenLabs Conversational AI (direct outbound calls)
    elevenlabs_api_key: SecretStr = Field(default=SecretStr(""), alias="ELEVENLABS_API_KEY")
    elevenlabs_phone_number_id: str = Field(default="", alias="ELEVENLABS_PHONE_NUMBER_ID")

    # V2: Separate agent IDs per call type
    elevenlabs_qualifier_agent_id: str = Field(
        default="", alias="ELEVENLABS_QUALIFIER_AGENT_ID"
    )
    elevenlabs_sales_agent_id: str = Field(
        default="", alias="ELEVENLABS_SALES_AGENT_ID"
    )
    elevenlabs_nurture_agent_id: str = Field(
        default="", alias="ELEVENLABS_NURTURE_AGENT_ID"
    )
    elevenlabs_auto_agent_id: str = Field(
        default="", alias="ELEVENLABS_AUTO_AGENT_ID"
    )

    # Perplexity Sonar (web research via OpenRouter)
    perplexity_model: str = "perplexity/sonar"
    # Uses openrouter_api_key -- no separate key needed

    # Research Sources (Custom APIs - placeholders)
    research_api_base_url: str = ""
    research_api_key: SecretStr = Field(default=SecretStr(""))

    # CHAMP Scoring Weights
    champ_weight_challenges: float = 0.30
    champ_weight_authority: float = 0.25
    champ_weight_money: float = 0.20
    champ_weight_prioritization: float = 0.25

    # CHAMP Tier Thresholds
    champ_tier_hot: int = 80
    champ_tier_warm: int = 60
    champ_tier_cool: int = 40

    # Worker Configuration
    worker_max_retries: int = 3
    worker_retry_delay: int = 300  # seconds
    worker_timeout: int = 600  # seconds

    # Rate Limiting
    email_rate_limit_per_hour: int = 100
    research_rate_limit_per_minute: int = 10

    @property
    def champ_weights(self) -> dict[str, float]:
        """Return CHAMP scoring weights as a dictionary."""
        return {
            "challenges": self.champ_weight_challenges,
            "authority": self.champ_weight_authority,
            "money": self.champ_weight_money,
            "prioritization": self.champ_weight_prioritization,
        }

    @property
    def champ_thresholds(self) -> dict[str, int]:
        """Return CHAMP tier thresholds as a dictionary."""
        return {
            "Hot": self.champ_tier_hot,
            "Warm": self.champ_tier_warm,
            "Cool": self.champ_tier_cool,
            "Cold": 0,
        }


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
