"""Knowledge Graph Entity Models (Node Types).

All entities are Pydantic v2 models that map to Neo4j nodes via Graphiti.
These represent the core domain objects in the ChampIQ system.
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from champiq_v2.utils.timezone import now_ist


def generate_id() -> str:
    """Generate a unique ID for entities."""
    return str(uuid4())


class ProspectState(str, Enum):
    """V2 prospect lifecycle states in the fixed pipeline."""

    NEW = "new"
    RESEARCHING = "researching"
    RESEARCHED = "researched"
    PITCHING = "pitching"
    EMAIL_SENT = "email_sent"
    WAITING_REPLY = "waiting_reply"
    FOLLOW_UP_SENT = "follow_up_sent"
    WAITING_FOLLOW_UP = "waiting_follow_up"
    QUALIFYING_CALL = "qualifying_call"
    INTERESTED = "interested"
    NOT_INTERESTED = "not_interested"
    SALES_CALL = "sales_call"
    NURTURE_CALL = "nurture_call"
    AUTO_CALL = "auto_call"
    QUALIFIED = "qualified"  # Terminal: HIL handoff


class InteractionType(str, Enum):
    """Types of interactions with prospects."""

    EMAIL_SENT = "email_sent"
    EMAIL_OPENED = "email_opened"
    EMAIL_CLICKED = "email_clicked"
    EMAIL_REPLIED = "email_replied"
    EMAIL_BOUNCED = "email_bounced"
    CALL_COMPLETED = "call_completed"
    CALL_NO_ANSWER = "call_no_answer"
    CALL_VOICEMAIL = "call_voicemail"
    MEETING_SCHEDULED = "meeting_scheduled"
    MEETING_COMPLETED = "meeting_completed"


class InteractionOutcome(str, Enum):
    """Outcome classification for interactions."""

    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    NO_RESPONSE = "no_response"


class PainPointCategory(str, Enum):
    """Categories of pain points that LakeB2B services address."""

    PIPELINE = "pipeline"  # Lead pipeline issues
    TARGETING = "targeting"  # Audience targeting problems
    DATA_QUALITY = "data_quality"  # Data accuracy/completeness
    ENGAGEMENT = "engagement"  # Low engagement rates
    COMPLIANCE = "compliance"  # GDPR/compliance challenges
    TECHNOLOGY = "technology"  # Tech stack gaps
    PROCESS = "process"  # Process inefficiencies
    TALENT = "talent"  # Hiring/recruiting challenges
    OPERATIONAL = "operational"  # General operational challenges
    OTHER = "other"  # Catch-all for uncategorised pain points


class ServiceVertical(str, Enum):
    """LakeB2B service verticals."""

    SALESTECH = "SalesTech"
    MARTECH = "MarTech"
    RECRUITTECH = "RecruitTech"
    GROWTHTECH = "GrowthTech"


class TriggerEventType(str, Enum):
    """Types of trigger events that indicate buying signals."""

    FUNDING = "funding"
    LEADERSHIP_CHANGE = "leadership_change"
    ACQUISITION = "acquisition"
    PRODUCT_LAUNCH = "product_launch"
    EXPANSION = "expansion"
    LAYOFF = "layoff"
    IPO = "ipo"
    PARTNERSHIP = "partnership"
    HIRING_SPREE = "hiring_spree"
    NEWS_MENTION = "news_mention"


# Backwards-compatible alias
TriggerType = TriggerEventType


class CHAMPScore(BaseModel):
    """CHAMP qualification score with 4 dimensions.

    Each dimension is scored 0-100 with a composite weighted average.
    """

    challenges: int = Field(ge=0, le=100, description="Pain point severity score")
    authority: int = Field(ge=0, le=100, description="Decision-making power score")
    money: int = Field(ge=0, le=100, description="Budget availability score")
    prioritization: int = Field(ge=0, le=100, description="Urgency/timing score")
    composite: float = Field(ge=0, le=100, description="Weighted average score")
    tier: str = Field(description="Routing tier: Hot|Warm|Cool|Cold")
    confidence: float = Field(ge=0, le=1, description="Score confidence level")
    reasoning: str = Field(default="", description="Explanation for the scores")

    # Individual dimension confidences
    challenges_confidence: float = Field(ge=0, le=1, default=0.5)
    authority_confidence: float = Field(ge=0, le=1, default=0.5)
    money_confidence: float = Field(ge=0, le=1, default=0.5)
    prioritization_confidence: float = Field(ge=0, le=1, default=0.5)


class Prospect(BaseModel):
    """Core prospect entity representing a potential lead.

    This is the central node in the knowledge graph, connected to
    companies, pain points, interactions, and decisions.
    """

    id: str = Field(default_factory=generate_id)
    name: str
    email: str
    title: Optional[str] = None
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None

    # Behavioral attributes
    timezone: Optional[str] = None
    communication_style: Optional[str] = None  # formal|casual|data_driven|narrative
    preferred_channel: Optional[str] = None  # email|phone|linkedin
    best_contact_time: Optional[str] = None

    # State management
    state: ProspectState = ProspectState.NEW
    champ_score: Optional[CHAMPScore] = None

    # Research completeness
    information_completeness: float = Field(ge=0, le=1, default=0.0)
    last_researched_at: Optional[datetime] = None

    # Engagement tracking
    positive_signals: int = Field(default=0)
    negative_signals: int = Field(default=0)
    total_interactions: int = Field(default=0)
    last_interaction_at: Optional[datetime] = None

    # Metadata
    source: Optional[str] = None  # How the prospect was acquired
    campaign_id: Optional[str] = None
    created_at: datetime = Field(default_factory=now_ist)
    updated_at: datetime = Field(default_factory=now_ist)


class Company(BaseModel):
    """Company entity representing the organization a prospect works for."""

    id: str = Field(default_factory=generate_id)
    name: str
    domain: str = Field(default="")
    industry: str = Field(default="unknown")
    website: Optional[str] = None
    sub_vertical: Optional[str] = None

    # Company size indicators
    employee_count: Optional[int] = None
    employee_count_range: Optional[str] = None  # 1-10, 11-50, 51-200, etc.
    revenue_band: Optional[str] = None  # <1M, 1-10M, 10-50M, etc.

    # Funding information
    funding_stage: Optional[str] = None  # seed, series_a, series_b, etc.
    recent_funding: Optional[float] = None  # Most recent funding amount
    total_funding: Optional[float] = None
    last_funding_date: Optional[datetime] = None
    last_funding_amount: Optional[float] = None

    # Technology stack
    tech_stack: list[str] = Field(default_factory=list)

    # Company intelligence
    recent_news: list[str] = Field(default_factory=list)
    growth_signals: list[str] = Field(default_factory=list)
    risk_signals: list[str] = Field(default_factory=list)

    # Location
    headquarters_city: Optional[str] = None
    headquarters_country: Optional[str] = None

    # Metadata
    linkedin_url: Optional[str] = None
    created_at: datetime = Field(default_factory=now_ist)
    updated_at: datetime = Field(default_factory=now_ist)


class PainPoint(BaseModel):
    """Identified pain point for a prospect or company."""

    id: str = Field(default_factory=generate_id)
    description: str
    category: PainPointCategory
    severity: int = Field(ge=1, le=10, description="Pain severity 1-10")

    # Evidence
    source_evidence: str = Field(default="research", description="How this pain point was identified")
    confidence: float = Field(ge=0, le=1, default=0.5)

    # Context
    keywords: list[str] = Field(default_factory=list)
    identified_via: str = Field(default="research")  # research|call|email_reply

    # Metadata
    identified_at: datetime = Field(default_factory=now_ist)


class LakeB2BService(BaseModel):
    """LakeB2B service offering that can solve pain points."""

    id: str = Field(default_factory=generate_id)
    vertical: ServiceVertical
    service_name: str
    description: str

    # Value proposition
    typical_roi: str
    value_proposition: str
    differentiators: list[str] = Field(default_factory=list)

    # Social proof
    case_studies: list[str] = Field(default_factory=list)
    customer_logos: list[str] = Field(default_factory=list)

    # Targeting
    ideal_company_size: Optional[str] = None
    ideal_industries: list[str] = Field(default_factory=list)


class Interaction(BaseModel):
    """Logged interaction with a prospect."""

    id: str = Field(default_factory=generate_id)
    type: InteractionType
    channel: str  # email|phone|linkedin|meeting
    timestamp: datetime = Field(default_factory=now_ist)

    # Outcome
    outcome: InteractionOutcome
    sentiment: Optional[float] = Field(ge=-1, le=1, default=None)

    # Content
    content_summary: str
    raw_content: Optional[str] = None

    # Response data (for emails)
    response_time_hours: Optional[float] = None

    # Call-specific data
    call_duration_seconds: Optional[int] = None
    transcript_summary: Optional[str] = None

    # Attribution
    campaign_id: Optional[str] = None
    worker_id: Optional[str] = None


class TriggerEvent(BaseModel):
    """Monitored trigger event indicating a buying signal."""

    id: str = Field(default_factory=generate_id)
    type: TriggerEventType
    date: datetime = Field(default_factory=now_ist)
    occurred_at: Optional[datetime] = None  # Alias populated by workers
    source: str = Field(default="research")  # news|linkedin|press_release|funding_db
    description: str

    # Impact assessment
    impact_assessment: str
    relevance_score: float = Field(ge=0, le=1)
    urgency_boost: int = Field(ge=0, le=20, default=0)

    # Company association
    company_id: Optional[str] = None

    # Metadata
    source_url: Optional[str] = None
    ingested_at: datetime = Field(default_factory=now_ist)


class Campaign(BaseModel):
    """Campaign entity for tracking outreach efforts."""

    id: str = Field(default_factory=generate_id)
    name: str
    channel: str  # email|multi_channel
    status: str  # draft|active|paused|completed

    # UTM tracking
    utm_source: str
    utm_medium: str
    utm_campaign: str
    utm_content: Optional[str] = None
    utm_term: Optional[str] = None

    # Targeting
    target_industries: list[str] = Field(default_factory=list)
    target_titles: list[str] = Field(default_factory=list)
    target_company_sizes: list[str] = Field(default_factory=list)

    # Metrics (denormalized for quick access)
    total_prospects: int = Field(default=0)
    emails_sent: int = Field(default=0)
    emails_opened: int = Field(default=0)
    emails_clicked: int = Field(default=0)
    emails_replied: int = Field(default=0)
    qualified_leads: int = Field(default=0)

    # Dates
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    created_at: datetime = Field(default_factory=now_ist)


class CallingAgentType(str, Enum):
    """Purpose of an ElevenLabs calling agent."""

    LEAD_QUALIFIER = "lead_qualifier"
    SALES = "sales"
    NURTURE = "nurture"
    CUSTOM = "custom"


class CallingAgent(BaseModel):
    """ElevenLabs calling agent configuration node in the knowledge graph.

    Each CallingAgent stores the ElevenLabs credentials + description for
    one conversational AI agent (e.g. 'CHAMP Lead Qualifier', 'Sales Closer').
    Storing agents in the graph means:
    - The decision engine can choose *which* agent to use per situation
    - Every Interaction node records which agent was used
    - The AI can factor agent performance into routing decisions over time
    """

    id: str = Field(default_factory=generate_id)
    name: str = Field(description="Human-readable name, e.g. 'CHAMP Lead Qualifier'")
    agent_type: CallingAgentType = Field(default=CallingAgentType.LEAD_QUALIFIER)
    description: str = Field(default="", description="What this agent does and when to use it")

    # ElevenLabs credentials (per-agent)
    elevenlabs_agent_id: str = Field(default="")
    elevenlabs_api_key: str = Field(default="")
    elevenlabs_phone_number_id: str = Field(default="")

    # Status
    is_active: bool = True

    # Metadata
    created_at: datetime = Field(default_factory=now_ist)
    updated_at: datetime = Field(default_factory=now_ist)
