"""CHAMP Scoring Engine.

Calculates CHAMP scores (Challenges, Authority, Money, Prioritization)
based on graph data and LLM analysis. Each dimension is scored 0-100
with a composite weighted average determining the routing tier.

Tiers:
- Hot (80-100): Immediate pitch, high priority
- Warm (60-79): Pitch with follow-up
- Cool (40-59): Nurture first, then pitch
- Cold (<40): Deep nurture or disqualify
"""

import logging
from datetime import datetime
from typing import Any, Optional

from champiq_v2.config import get_settings
from champiq_v2.graph.entities import CHAMPScore, PainPointCategory
from champiq_v2.graph.service import GraphService, get_graph_service
from champiq_v2.llm.service import LLMService, get_llm_service

logger = logging.getLogger(__name__)


class CHAMPScorer:
    """CHAMP scoring engine for prospect qualification.

    Calculates scores across 4 dimensions:
    - Challenges: Do they have pain points we can solve?
    - Authority: Can they make or influence buying decisions?
    - Money: Does the company have budget?
    - Prioritization: Is solving this a current priority?
    """

    # Title-based authority scoring
    TITLE_AUTHORITY_SCORES = {
        # C-Suite (95-100)
        "ceo": 100, "chief executive": 100, "founder": 95, "co-founder": 95,
        "cto": 95, "chief technology": 95, "cmo": 95, "chief marketing": 95,
        "cfo": 95, "chief financial": 95, "cro": 95, "chief revenue": 95,
        "coo": 95, "chief operating": 95, "president": 95,
        # VP Level (75-85)
        "vp": 80, "vice president": 80, "svp": 85, "senior vice president": 85,
        "evp": 85, "executive vice president": 85,
        # Director Level (60-75)
        "director": 65, "senior director": 70, "head of": 75,
        # Manager Level (40-55)
        "manager": 45, "senior manager": 50, "group manager": 55,
        # Lead/Senior (25-40)
        "lead": 35, "team lead": 35, "senior": 30,
        # Individual Contributor (15-25)
        "specialist": 20, "analyst": 20, "associate": 20, "coordinator": 20,
    }

    # Funding stage to budget score mapping
    FUNDING_BUDGET_SCORES = {
        "ipo": 95, "public": 95,
        "series_d": 90, "series_e": 90, "series_f": 90,
        "series_c": 85,
        "series_b": 75,
        "series_a": 60,
        "seed": 45,
        "pre_seed": 35,
        "bootstrapped": 55,  # Could have revenue
        "unknown": 50,
    }

    # Trigger event urgency boosts
    TRIGGER_URGENCY_BOOSTS = {
        "funding": 20,
        "leadership_change": 15,
        "acquisition": 15,
        "expansion": 12,
        "product_launch": 10,
        "partnership": 8,
        "ipo": 20,
        "layoff": -10,  # Could reduce budget
    }

    def __init__(
        self,
        graph_service: Optional[GraphService] = None,
        llm_service: Optional[LLMService] = None,
    ):
        self.settings = get_settings()
        self._graph = graph_service
        self._llm = llm_service

    async def _get_graph(self) -> GraphService:
        if self._graph is None:
            self._graph = await get_graph_service()
        return self._graph

    def _get_llm(self) -> LLMService:
        if self._llm is None:
            self._llm = get_llm_service()
        return self._llm

    async def calculate(self, prospect_id: str) -> CHAMPScore:
        """Calculate full CHAMP score for a prospect.

        Queries the graph for all relevant data and computes scores
        for each dimension with confidence levels.
        """
        graph = await self._get_graph()
        context_obj = await graph.get_prospect_context(prospect_id)

        if not context_obj:
            logger.warning("No context found for prospect %s", prospect_id)
            return self._empty_score()

        # Convert ProspectContext to dict for scoring methods
        context = {
            "prospect": context_obj.prospect.model_dump() if context_obj.prospect else {},
            "company": context_obj.company.model_dump() if context_obj.company else {},
            "pain_points": [pp.model_dump() for pp in context_obj.pain_points],
            "interactions": [i.model_dump() for i in context_obj.interactions],
            "recent_trigger_events": [te.model_dump() for te in context_obj.trigger_events],
            "service_matches": context_obj.service_matches,
        }

        # Build extended context dict with derived fields
        ctx = self._build_context_dict(context_obj, context)

        # Calculate each dimension
        challenges_score, challenges_conf = await self._score_challenges(ctx)
        authority_score, authority_conf = self._score_authority(ctx)
        money_score, money_conf = self._score_money(ctx)
        prioritization_score, prioritization_conf = await self._score_prioritization(ctx)

        # Calculate weighted composite
        weights = self.settings.champ_weights
        composite = (
            challenges_score * weights["challenges"]
            + authority_score * weights["authority"]
            + money_score * weights["money"]
            + prioritization_score * weights["prioritization"]
        )

        # Determine tier
        tier = self._determine_tier(composite)

        # Calculate overall confidence
        confidence = (
            challenges_conf * weights["challenges"]
            + authority_conf * weights["authority"]
            + money_conf * weights["money"]
            + prioritization_conf * weights["prioritization"]
        )

        # Generate reasoning
        reasoning = await self._generate_reasoning(
            ctx,
            {
                "challenges": challenges_score,
                "authority": authority_score,
                "money": money_score,
                "prioritization": prioritization_score,
            },
        )

        score = CHAMPScore(
            challenges=int(challenges_score),
            authority=int(authority_score),
            money=int(money_score),
            prioritization=int(prioritization_score),
            composite=round(composite, 1),
            tier=tier,
            confidence=round(confidence, 2),
            reasoning=reasoning,
            challenges_confidence=round(challenges_conf, 2),
            authority_confidence=round(authority_conf, 2),
            money_confidence=round(money_conf, 2),
            prioritization_confidence=round(prioritization_conf, 2),
        )

        return score

    def _build_context_dict(self, context_obj, context: dict[str, Any]) -> dict[str, Any]:
        """Build an extended dict suitable for scoring from ProspectContext + base dict.

        Adds derived fields (counts, signal tallies, recent triggers) on top
        of the base context dict produced by calculate().
        """
        positive_interactions = len(
            [i for i in context_obj.interactions if i.outcome.value == "positive"]
        )
        negative_interactions = len(
            [i for i in context_obj.interactions if i.outcome.value == "negative"]
        )

        # Get recent trigger events (last 30 days)
        recent_triggers = [
            te
            for te in context_obj.trigger_events
            if (datetime.utcnow() - te.date).days <= 30
        ]

        # Start with the base context and add derived fields
        ctx = dict(context)
        ctx.update({
            "pain_point_count": len(context_obj.pain_points),
            "interaction_count": len(context_obj.interactions),
            "positive_signals": positive_interactions,
            "negative_signals": negative_interactions,
            "recent_trigger_events": [
                te.model_dump(mode="json") for te in recent_triggers
            ],
        })
        return ctx

    async def _score_challenges(self, context: dict[str, Any]) -> tuple[float, float]:
        """Score based on identified pain points and service fit.

        Factors:
        - Number of pain points identified
        - Severity of pain points
        - How well our services match their pain points
        """
        pain_points = context.get("pain_points", [])
        service_matches = context.get("service_matches", [])

        if not pain_points:
            # No pain points = low score, low confidence
            return 25.0, 0.3

        # Base score from pain point count and severity
        total_severity = sum(pp.get("severity", 5) for pp in pain_points)
        avg_severity = total_severity / len(pain_points)

        # Pain point count bonus (diminishing returns)
        count_bonus = min(len(pain_points) * 8, 30)

        # Service match bonus
        match_bonus = 0
        if service_matches:
            avg_fit = sum(m.get("fit_score", 0.5) for m in service_matches) / len(service_matches)
            match_bonus = avg_fit * 20  # Up to 20 points for perfect fit

        # Calculate base score
        base_score = 30 + (avg_severity * 3) + count_bonus + match_bonus
        score = min(base_score, 100)

        # Confidence based on evidence quality
        confidence = min(0.4 + (len(pain_points) * 0.1) + (len(service_matches) * 0.1), 0.95)

        return score, confidence

    def _score_authority(self, context: dict[str, Any]) -> tuple[float, float]:
        """Score based on decision-making authority.

        Factors:
        - Job title / level
        - Seniority indicators
        """
        prospect = context.get("prospect", {})
        title = (prospect.get("title") or "").lower()

        if not title:
            return 40.0, 0.3  # Unknown title, assume middle ground

        # Find best matching title score
        score = 40  # Default for unknown titles
        for keyword, title_score in self.TITLE_AUTHORITY_SCORES.items():
            if keyword in title:
                score = max(score, title_score)

        # Confidence based on title clarity
        confidence = 0.9 if score >= 60 else 0.7 if score >= 40 else 0.5

        return float(score), confidence

    def _score_money(self, context: dict[str, Any]) -> tuple[float, float]:
        """Score based on budget availability indicators.

        Factors:
        - Company funding stage
        - Employee count (proxy for company size)
        - Recent funding events
        - Revenue signals
        """
        company = context.get("company") or {}

        # Funding stage score
        funding_stage = (company.get("funding_stage") or "unknown").lower()
        base_score = self.FUNDING_BUDGET_SCORES.get(funding_stage, 50)

        # Employee count adjustments
        employee_count = company.get("employee_count") or 0
        if employee_count > 1000:
            base_score = min(base_score + 15, 100)
        elif employee_count > 500:
            base_score = min(base_score + 12, 100)
        elif employee_count > 200:
            base_score = min(base_score + 8, 100)
        elif employee_count > 50:
            base_score = min(base_score + 5, 100)

        # Recent funding boost
        recent_triggers = context.get("recent_trigger_events", [])
        funding_events = [t for t in recent_triggers if t.get("type") == "funding"]
        if funding_events:
            base_score = min(base_score + 15, 100)

        # Confidence based on data availability
        has_funding_info = funding_stage != "unknown"
        has_size_info = employee_count > 0
        confidence = 0.5 + (0.2 if has_funding_info else 0) + (0.2 if has_size_info else 0)

        return float(base_score), min(confidence, 0.9)

    async def _score_prioritization(self, context: dict[str, Any]) -> tuple[float, float]:
        """Score based on urgency and timing signals.

        Factors:
        - Trigger events (funding, leadership changes, etc.)
        - Recent engagement/interest signals
        - Competitive pressure indicators
        - Expressed urgency in communications
        """
        # Base score
        score = 50.0

        # Trigger event boosts
        recent_triggers = context.get("recent_trigger_events", [])
        trigger_boost = 0
        for event in recent_triggers:
            event_type = event.get("type", "")
            trigger_boost += self.TRIGGER_URGENCY_BOOSTS.get(event_type, 0)
        score += min(trigger_boost, 30)  # Cap at 30 point boost

        # Engagement recency boost
        positive_signals = context.get("positive_signals", 0)
        if positive_signals > 0:
            score += min(positive_signals * 5, 15)

        # Check for expressed urgency in interactions
        interactions = context.get("interactions", [])
        # This would ideally check sentiment/content, simplified here
        recent_positive = len([
            i for i in interactions[-5:]
            if i.get("outcome") == "positive"
        ])
        if recent_positive > 0:
            score += 10

        score = min(score, 100)

        # Confidence based on signal availability
        has_triggers = len(recent_triggers) > 0
        has_engagement = len(interactions) > 0
        confidence = 0.4 + (0.2 if has_triggers else 0) + (0.2 if has_engagement else 0)

        return score, confidence

    def _determine_tier(self, composite: float) -> str:
        """Determine routing tier from composite score."""
        thresholds = self.settings.champ_thresholds
        if composite >= thresholds["Hot"]:
            return "Hot"
        elif composite >= thresholds["Warm"]:
            return "Warm"
        elif composite >= thresholds["Cool"]:
            return "Cool"
        else:
            return "Cold"

    async def _generate_reasoning(
        self, context: dict[str, Any], scores: dict[str, float]
    ) -> str:
        """Generate human-readable reasoning for the scores."""
        prospect = context.get("prospect", {})
        company = context.get("company") or {}
        pain_points = context.get("pain_points", [])

        reasoning_parts = []

        # Challenges reasoning
        if scores["challenges"] >= 70:
            reasoning_parts.append(
                f"Strong pain point fit: {len(pain_points)} pain points identified"
            )
        elif scores["challenges"] < 40:
            reasoning_parts.append("Limited pain point visibility")

        # Authority reasoning
        title = prospect.get("title", "Unknown")
        if scores["authority"] >= 80:
            reasoning_parts.append(f"High authority: {title}")
        elif scores["authority"] < 40:
            reasoning_parts.append(f"Lower authority level: {title}")

        # Money reasoning
        funding = company.get("funding_stage", "unknown")
        employees = company.get("employee_count", 0)
        if scores["money"] >= 75:
            reasoning_parts.append(
                f"Strong budget indicators: {funding}, {employees}+ employees"
            )

        # Prioritization reasoning
        triggers = context.get("recent_trigger_events", [])
        if triggers:
            trigger_types = [t.get("type") for t in triggers[:2]]
            reasoning_parts.append(f"Recent triggers: {', '.join(trigger_types)}")

        return "; ".join(reasoning_parts) if reasoning_parts else "Standard scoring applied"

    def _empty_score(self) -> CHAMPScore:
        """Return an empty/default CHAMP score."""
        return CHAMPScore(
            challenges=25,
            authority=25,
            money=25,
            prioritization=25,
            composite=25.0,
            tier="Cold",
            confidence=0.2,
            reasoning="Insufficient data for scoring",
            challenges_confidence=0.2,
            authority_confidence=0.2,
            money_confidence=0.2,
            prioritization_confidence=0.2,
        )

    async def recalculate_after_interaction(
        self, prospect_id: str, interaction_outcome: str
    ) -> CHAMPScore:
        """Recalculate CHAMP score after a new interaction.

        Adjusts scores based on interaction outcomes:
        - Positive: Boost prioritization
        - Negative: May reduce scores
        - Neutral: Minimal change
        """
        # Get fresh calculation
        score = await self.calculate(prospect_id)

        # Adjust based on interaction
        if interaction_outcome == "positive":
            # Boost prioritization for engaged prospects
            score.prioritization = min(score.prioritization + 10, 100)
            score.composite = self._recalculate_composite(score)
            score.tier = self._determine_tier(score.composite)
        elif interaction_outcome == "negative":
            # Reduce prioritization for disengaged
            score.prioritization = max(score.prioritization - 15, 0)
            score.composite = self._recalculate_composite(score)
            score.tier = self._determine_tier(score.composite)

        return score

    def _recalculate_composite(self, score: CHAMPScore) -> float:
        """Recalculate composite from dimension scores."""
        weights = self.settings.champ_weights
        return round(
            score.challenges * weights["challenges"]
            + score.authority * weights["authority"]
            + score.money * weights["money"]
            + score.prioritization * weights["prioritization"],
            1,
        )


# Singleton instance
_champ_scorer: Optional[CHAMPScorer] = None


async def get_champ_scorer() -> CHAMPScorer:
    """Get the CHAMP scorer singleton."""
    global _champ_scorer
    if _champ_scorer is None:
        _champ_scorer = CHAMPScorer()
    return _champ_scorer
