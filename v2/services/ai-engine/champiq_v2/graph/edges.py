"""Knowledge Graph Edge Models (Relationship Types).

All edges are Pydantic v2 models that map to Neo4j relationships via Graphiti.
Every edge includes temporal metadata for point-in-time queries.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from champiq_v2.utils.timezone import now_ist


class TemporalEdge(BaseModel):
    """Base class for all edges with temporal metadata.

    All relationships in the knowledge graph are temporal, meaning they
    track when the relationship was valid and when it was ingested.
    This enables:
    - Point-in-time historical queries
    - Tracking relationship changes over time
    - Learning from historical patterns
    """

    valid_from: datetime = Field(
        default_factory=now_ist, description="When this relationship became valid"
    )
    valid_to: Optional[datetime] = Field(
        default=None, description="When this relationship ended (None = still valid)"
    )
    ingested_at: datetime = Field(
        default_factory=now_ist, description="When this was added to the graph"
    )
    confidence: float = Field(
        ge=0, le=1, default=0.8, description="Confidence in this relationship"
    )
    source: str = Field(
        default="system", description="How this relationship was established"
    )

    @property
    def is_active(self) -> bool:
        """Check if this relationship is currently active."""
        return self.valid_to is None


class WorksAt(TemporalEdge):
    """Prospect -> Company relationship.

    Represents employment relationship with role details.
    """

    role: str = Field(description="Job title/role at the company")
    authority_level: int = Field(
        ge=1, le=5, default=3, description="1=IC, 2=Lead, 3=Manager, 4=Director/VP, 5=C-Level"
    )
    department: Optional[str] = None
    start_date: Optional[datetime] = None
    is_decision_maker: bool = False
    reports_to_title: Optional[str] = None


class HasPainPoint(TemporalEdge):
    """Prospect|Company -> PainPoint relationship.

    Links entities to their identified pain points.
    """

    severity: int = Field(ge=1, le=10, description="Pain severity for this entity")
    identified_via: str = Field(
        default="research", description="How identified: research|call|email_reply|news"
    )
    verbatim_quote: Optional[str] = Field(
        default=None, description="Direct quote if from conversation"
    )
    is_primary: bool = Field(default=False, description="Is this the primary pain point?")


class SolvedBy(TemporalEdge):
    """PainPoint -> LakeB2BService relationship.

    Maps pain points to LakeB2B service solutions.
    """

    expected_roi: str = Field(description="Expected ROI from this solution")
    fit_score: float = Field(ge=0, le=1, description="How well the service fits the pain")
    case_study_refs: list[str] = Field(
        default_factory=list, description="Relevant case study references"
    )
    implementation_complexity: str = Field(
        default="medium", description="low|medium|high"
    )
    time_to_value: Optional[str] = Field(
        default=None, description="Expected time to see value"
    )


class PitchedWith(TemporalEdge):
    """Prospect -> Campaign relationship.

    Tracks which campaigns/pitches have been sent to a prospect.
    """

    variant_used: str = Field(description="Pitch variant: primary|secondary|nurture")
    pitch_angle: str = Field(description="The angle/approach used in this pitch")
    send_date: datetime = Field(default_factory=now_ist)
    email_subject: Optional[str] = None
    email_body_hash: Optional[str] = Field(
        default=None, description="Hash of email body for deduplication"
    )
    utm_params: Optional[dict] = None


class InteractedVia(TemporalEdge):
    """Prospect -> Interaction relationship.

    Links prospects to their interactions.
    """

    channel: str = Field(description="Channel of interaction: email|phone|linkedin|meeting")
    response_type: str = Field(description="Type of response received")
    sentiment_score: Optional[float] = Field(
        ge=-1, le=1, default=None, description="Sentiment: -1 negative to 1 positive"
    )
    champ_signals_extracted: list[str] = Field(
        default_factory=list, description="CHAMP signals identified from interaction"
    )
    follow_up_required: bool = False


class SimilarTo(TemporalEdge):
    """Prospect -> Prospect relationship.

    Used for lookalike targeting and pattern matching.
    """

    similarity_dimensions: list[str] = Field(
        description="Dimensions of similarity: industry|title|pain_points|behavior"
    )
    similarity_score: float = Field(ge=0, le=1, description="Overall similarity score")
    shared_pain_points: list[str] = Field(default_factory=list)
    shared_behaviors: list[str] = Field(default_factory=list)


class BelongsTo(TemporalEdge):
    """Company -> Industry relationship.

    Categorizes companies by industry.
    """

    market_position: str = Field(
        default="challenger", description="Market position: leader|challenger|niche|emerging"
    )
    is_primary_industry: bool = True
    industry_segment: Optional[str] = None


class TriggeredBy(TemporalEdge):
    """TriggerEvent -> Company relationship.

    Links trigger events to the companies they affect.
    """

    relevance_score: float = Field(ge=0, le=1, description="How relevant to sales")
    action_taken: Optional[str] = Field(
        default=None, description="What action was triggered by this event"
    )
    urgency_created: bool = False
    opportunity_type: Optional[str] = Field(
        default=None, description="Type of opportunity: expansion|new_budget|pain_increase"
    )


class DecidedAction(TemporalEdge):
    """Decision -> Prospect relationship.

    Links decisions to the prospects they affect.
    """

    action_type: str = Field(description="Type of action decided: pitch|call|nurture|qualify|disqualify")
    outcome: Optional[str] = Field(
        default=None, description="Outcome of the action if executed"
    )
    was_overridden: bool = False
    override_by: Optional[str] = Field(
        default=None, description="Who overrode the decision"
    )
    execution_timestamp: Optional[datetime] = None


class CompetesWith(TemporalEdge):
    """Company -> Company relationship.

    Tracks competitive relationships between companies.
    """

    competition_intensity: str = Field(
        default="moderate", description="low|moderate|high|direct"
    )
    overlapping_markets: list[str] = Field(default_factory=list)
    competitive_advantage: Optional[str] = None


class ReportsTo(TemporalEdge):
    """Prospect -> Prospect relationship (within same company).

    Organizational hierarchy relationship.
    """

    relationship_type: str = Field(
        default="direct", description="direct|dotted_line|skip_level"
    )
    influence_level: int = Field(
        ge=1, le=5, default=3, description="How much influence in decisions"
    )
