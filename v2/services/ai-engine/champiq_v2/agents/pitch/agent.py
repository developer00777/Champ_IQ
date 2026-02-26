"""Pitch Agent - Generates personalised multi-variant outreach content.

The Pitch Agent is responsible for:
1. Reading prospect + company context from the knowledge graph
2. Generating three email variants (primary pitch, secondary angle, nurture)
3. Generating a call script tailored to identified CHAMP gaps
4. Logging generated pitches as interactions in the graph
5. Returning structured pitch assets ready for the SMTP / Voice workers

All generation uses the LLM service with graceful fallback to
context-aware templates when the LLM is offline.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from champiq_v2.utils.timezone import now_ist
from uuid import uuid4

from champiq_v2.config import get_settings
from champiq_v2.graph.entities import Interaction, InteractionOutcome, InteractionType
from champiq_v2.graph.service import get_graph_service
from champiq_v2.llm.service import get_llm_service
from champiq_v2.workers.base import ActivityEvent, activity_stream

logger = logging.getLogger(__name__)

# Availability CTA appended to all email variants in V2
AVAILABILITY_CTA = "\n\nWould any of these times work for a quick 15-minute call? I'm flexible and happy to adjust."


# --- Data Models --------------------------------------------------------------


@dataclass
class EmailVariant:
    """A single email variant."""

    variant: str          # primary | secondary | nurture
    subject: str
    body: str
    tone: str = "consultative"
    generated_by: str = "llm"   # llm | template


@dataclass
class CallScript:
    """Generated voice call script."""

    call_type: str        # discovery | qualification | follow_up
    script: str
    key_questions: list[str] = field(default_factory=list)
    objection_handlers: dict[str, str] = field(default_factory=dict)
    generated_by: str = "llm"


@dataclass
class PitchPlan:
    """Input plan describing what to generate."""

    prospect_id: str
    campaign_context: Optional[str] = None   # User-supplied goal / context
    tone: str = "consultative"               # consultative | direct | friendly
    generate_emails: bool = True
    generate_call_script: bool = True
    email_variants: list[str] = field(
        default_factory=lambda: ["primary", "secondary", "nurture"]
    )
    call_type: str = "discovery"
    champ_gaps: list[str] = field(default_factory=list)


@dataclass
class PitchResult:
    """Complete pitch package for a prospect."""

    prospect_id: str
    generated_at: datetime
    emails: list[EmailVariant] = field(default_factory=list)
    call_script: Optional[CallScript] = None
    confidence: float = 0.0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "prospect_id": self.prospect_id,
            "generated_at": self.generated_at.isoformat(),
            "emails": [
                {
                    "variant": e.variant,
                    "subject": e.subject,
                    "body": e.body,
                    "tone": e.tone,
                    "generated_by": e.generated_by,
                }
                for e in self.emails
            ],
            "call_script": {
                "call_type": self.call_script.call_type,
                "script": self.call_script.script,
                "key_questions": self.call_script.key_questions,
                "objection_handlers": self.call_script.objection_handlers,
                "generated_by": self.call_script.generated_by,
            } if self.call_script else None,
            "confidence": self.confidence,
            "errors": self.errors,
        }


# --- Agent --------------------------------------------------------------------


class PitchAgent:
    """Pitch Agent that generates personalised outreach content.

    The agent:
    1. Fetches full prospect/company context from the knowledge graph
    2. Uses the LLM to generate email variants and call scripts
    3. Falls back to context-aware templates when LLM is unavailable
    4. Logs the generated pitches as interactions in the graph
    5. Returns a PitchResult with all assets

    Usage::

        agent = get_pitch_agent()
        plan = PitchPlan(
            prospect_id="...",
            campaign_context="Selling LakeB2B data services...",
        )
        result = await agent.generate(plan)
    """

    def __init__(self):
        self.settings = get_settings()
        self._llm = None

    def _get_llm(self):
        if self._llm is None:
            self._llm = get_llm_service()
        return self._llm

    # -- Main entry point ------------------------------------------------------

    async def generate(self, plan: PitchPlan) -> PitchResult:
        """Generate a complete pitch package for a prospect.

        Args:
            plan: PitchPlan specifying what to generate.

        Returns:
            PitchResult with email variants and/or call script.
        """
        logger.info("Generating pitch for prospect %s", plan.prospect_id)

        result = PitchResult(
            prospect_id=plan.prospect_id,
            generated_at=now_ist(),
        )

        # Emit start event
        await activity_stream.emit(ActivityEvent(
            event_type="pitch_started",
            worker_type="pitch",
            prospect_id=plan.prospect_id,
            data={"variants": plan.email_variants, "call_type": plan.call_type},
        ))

        # Load context from graph
        context = await self._load_context(plan.prospect_id)
        if plan.campaign_context:
            context["campaign_context"] = plan.campaign_context

        prospect = context.get("prospect") or {}
        name = (
            prospect.get("name", "there")
            if isinstance(prospect, dict)
            else getattr(prospect, "name", "there")
        )
        company = context.get("company") or {}
        company_name = (
            company.get("name", "")
            if isinstance(company, dict)
            else getattr(company, "name", "")
        )

        # Generate emails
        if plan.generate_emails:
            for variant in plan.email_variants:
                email_variant = await self._generate_email(
                    context, variant, plan.tone, name, company_name, plan.campaign_context
                )
                result.emails.append(email_variant)

        # Generate call script
        if plan.generate_call_script:
            script = await self._generate_call_script(
                context, plan.call_type, plan.champ_gaps, name, company_name
            )
            result.call_script = script

        # Calculate confidence
        result.confidence = self._calculate_confidence(result)

        # Log to graph
        await self._log_pitch(plan.prospect_id, result)

        # Emit completion event
        await activity_stream.emit(ActivityEvent(
            event_type="pitch_completed",
            worker_type="pitch",
            prospect_id=plan.prospect_id,
            data=result.to_dict(),
        ))

        return result

    # -- Context loading -------------------------------------------------------

    async def _load_context(self, prospect_id: str) -> dict[str, Any]:
        """Load full prospect context from the knowledge graph."""
        try:
            graph = await get_graph_service()
            ctx = await graph.get_prospect_context(prospect_id)
            if not ctx:
                return {}
            return {
                "prospect": ctx.prospect.model_dump(mode="json") if ctx.prospect else {},
                "company": ctx.company.model_dump(mode="json") if ctx.company else {},
                "pain_points": [pp.model_dump(mode="json") for pp in ctx.pain_points],
                "champ_score": ctx.prospect.champ_score.model_dump(mode="json") if ctx.prospect and ctx.prospect.champ_score else {},
            }
        except Exception as e:
            logger.warning("Could not load graph context: %s", e)
            return {}

    # -- Email generation ------------------------------------------------------

    async def _generate_email(
        self,
        context: dict[str, Any],
        variant: str,
        tone: str,
        name: str,
        company_name: str,
        campaign_context: Optional[str],
    ) -> EmailVariant:
        """Generate a single email variant, with LLM fallback."""
        llm = self._get_llm()
        try:
            raw = await llm.generate_email(context, variant, tone=tone)
            body = raw.get("body", "") + AVAILABILITY_CTA
            return EmailVariant(
                variant=variant,
                subject=raw.get("subject", f"A thought for {name}"),
                body=body,
                tone=tone,
                generated_by="llm",
            )
        except Exception as e:
            logger.warning("LLM email generation failed for variant %s: %s", variant, e)
            subject, body = self._fallback_email(variant, name, company_name, campaign_context)
            return EmailVariant(
                variant=variant,
                subject=subject,
                body=body,
                tone=tone,
                generated_by="template",
            )

    def _fallback_email(
        self,
        variant: str,
        name: str,
        company_name: str,
        campaign_context: Optional[str],
    ) -> tuple[str, str]:
        """Return a context-aware (subject, body) when LLM is unavailable."""
        at_company = f" at {company_name}" if company_name else ""
        ctx_section = f"\n\nContext we're working from:\n{campaign_context.strip()}\n" if campaign_context else ""

        subjects = {
            "primary": f"A quick idea for {name}{at_company}",
            "secondary": f"One more thought, {name} -- worth 2 mins?",
            "nurture": f"Something useful for {name}{at_company} -- no pitch, promise",
        }

        bodies = {
            "primary": f"""Hi {name},

I came across your profile{at_company} and wanted to reach out directly.{ctx_section}
We work with companies like yours to help them get more from their data -- specifically around lead quality, contact accuracy, and pipeline velocity.

I'd love to share a few ideas that have worked well for others in your space. Would a quick 15-minute conversation be worth it?

If so, what time works best for you this week? Or if now is easier, I can make it happen.

Best,
The LakeB2B Team{AVAILABILITY_CTA}""",

            "secondary": f"""Hi {name},

I wanted to follow up from a slightly different angle.{ctx_section}
Rather than a broad conversation, I thought it might be more useful to share one specific insight -- how companies like {company_name or 'yours'} are rethinking data enrichment in 2026 and what's actually moving the needle.

Happy to send over a short summary, or jump on a call if you'd prefer. What works better for you?

Best,
The LakeB2B Team{AVAILABILITY_CTA}""",

            "nurture": f"""Hi {name},

No pitch here -- just sharing something you might find genuinely useful.{ctx_section}
We've been tracking how top B2B teams are approaching prospect research differently in 2026 -- moving away from static lists toward dynamic, intent-driven signals.

If you're curious about what that looks like in practice, I'm happy to walk you through it. No obligation, just a conversation.

Let me know if you'd like to set something up -- even a 10-minute call works.

Best,
The LakeB2B Team{AVAILABILITY_CTA}""",
        }

        subject = subjects.get(variant, subjects["primary"])
        body = bodies.get(variant, bodies["primary"])
        return subject, body

    # -- Call script generation ------------------------------------------------

    async def _generate_call_script(
        self,
        context: dict[str, Any],
        call_type: str,
        champ_gaps: list[str],
        name: str,
        company_name: str,
    ) -> CallScript:
        """Generate a call script, with LLM fallback."""
        llm = self._get_llm()
        pain_points = context.get("pain_points") or []
        champ_score = context.get("champ_score") or {}

        # Build gap questions for the script
        gap_question_map = {
            "challenges": "What are the biggest data quality challenges you're facing right now?",
            "authority": "Who else on your team would typically be involved in evaluating a data solution?",
            "money": "Do you have budget allocated for improving your lead data quality this year?",
            "prioritization": "Where does improving data accuracy sit on your priority list right now?",
        }
        key_questions = [
            gap_question_map.get(gap, gap_question_map["challenges"])
            for gap in (champ_gaps or ["challenges"])
        ]

        prompt = f"""You are a senior B2B sales rep at LakeB2B, calling {name} at {company_name}.
Call type: {call_type}
CHAMP gaps to cover: {', '.join(champ_gaps) if champ_gaps else 'general discovery'}
Known pain points: {[pp.get('description', str(pp)) if isinstance(pp, dict) else str(pp) for pp in pain_points[:3]]}

Write a natural, consultative {call_type} call script (150-250 words). Include:
- Warm opener referencing the email they received
- 2-3 open-ended discovery questions focused on CHAMP gaps
- A soft close asking for a follow-up or next step

Tone: helpful expert, not pushy salesperson.
Respond with ONLY the script text, no JSON."""

        try:
            script_text = await llm.complete(prompt, max_tokens=800, temperature=0.7)
            return CallScript(
                call_type=call_type,
                script=script_text.strip(),
                key_questions=key_questions,
                objection_handlers={
                    "not interested": "I completely understand -- mind if I ask what's taking priority right now?",
                    "too busy": "No problem at all. Would 5 minutes next week work instead?",
                    "already have a solution": "That's great -- curious, how are you finding the data accuracy?",
                },
                generated_by="llm",
            )
        except Exception as e:
            logger.warning("LLM call script generation failed: %s", e)
            return self._fallback_call_script(call_type, name, company_name, key_questions)

    def _fallback_call_script(
        self,
        call_type: str,
        name: str,
        company_name: str,
        key_questions: list[str],
    ) -> CallScript:
        """Context-aware fallback call script."""
        questions_formatted = "\n".join(f"- {q}" for q in key_questions)
        scripts = {
            "discovery": f"""Hi {name}, this is [Agent] from LakeB2B. Hope I'm not catching you at a bad time!

I sent over an email recently about how we help companies like {company_name or 'yours'} improve their B2B data quality and reach the right decision-makers faster.

Do you have a couple of minutes to chat?

[If yes]

Great! I'd love to learn a bit more about your current setup. Let me ask:

{questions_formatted}

[Listen, take notes]

Based on what you've shared, I think there might be a genuinely good fit here. Would it make sense to set up a short follow-up where I can share some specific examples?""",

            "qualification": f"""Hi {name}, this is [Agent] from LakeB2B following up on our earlier conversation.

I wanted to quickly revisit a couple of things you mentioned to make sure we're focusing on the right areas for you.

{questions_formatted}

[Based on answers, position LakeB2B's value accordingly]

It sounds like [summarise their situation]. Here's how we've helped companies in a similar position...

Does it make sense to move this conversation forward?""",

            "follow_up": f"""Hi {name}, it's [Agent] from LakeB2B again.

I know you've been thinking things over since we last spoke. I just wanted to check in briefly and see if any questions have come up on your end.

Is there anything specific I can clarify or help you think through?""",
        }

        script = scripts.get(call_type, scripts["discovery"])
        return CallScript(
            call_type=call_type,
            script=script,
            key_questions=key_questions,
            objection_handlers={
                "not interested": "I completely understand -- mind if I ask what's taking priority right now?",
                "too busy": "No problem at all. Would 5 minutes next week work instead?",
                "already have a solution": "That's great -- curious, how are you finding the data accuracy?",
            },
            generated_by="template",
        )

    # -- Graph logging ---------------------------------------------------------

    async def _log_pitch(self, prospect_id: str, result: PitchResult) -> None:
        """Log generated pitch as an interaction in the knowledge graph."""
        try:
            graph = await get_graph_service()
            variants_summary = ", ".join(e.variant for e in result.emails)
            interaction = Interaction(
                type=InteractionType.EMAIL_SENT,  # closest available type
                channel="pitch_engine",
                outcome=InteractionOutcome.NEUTRAL,
                content_summary=(
                    f"Generated pitch: variants=[{variants_summary}], "
                    f"call_script={bool(result.call_script)}, "
                    f"confidence={result.confidence:.2f}"
                ),
            )
            await graph.create_interaction(prospect_id, interaction)
        except Exception as e:
            logger.warning("Could not log pitch to graph: %s", e)

    # -- Helpers ---------------------------------------------------------------

    def _calculate_confidence(self, result: PitchResult) -> float:
        """Estimate confidence in the generated pitch quality."""
        score = 0.0
        llm_emails = sum(1 for e in result.emails if e.generated_by == "llm")
        total_emails = len(result.emails) or 1
        score += (llm_emails / total_emails) * 0.6

        if result.call_script:
            score += 0.2 if result.call_script.generated_by == "llm" else 0.1

        if result.emails:
            score += 0.2

        return round(min(1.0, score), 2)

    async def quick_pitch(
        self,
        prospect_id: str,
        campaign_context: Optional[str] = None,
    ) -> PitchResult:
        """Convenience method: generate all variants + call script in one call."""
        plan = PitchPlan(
            prospect_id=prospect_id,
            campaign_context=campaign_context,
        )
        return await self.generate(plan)


# -- Singleton -----------------------------------------------------------------

_pitch_agent: Optional[PitchAgent] = None


def get_pitch_agent() -> PitchAgent:
    """Get the global PitchAgent singleton."""
    global _pitch_agent
    if _pitch_agent is None:
        _pitch_agent = PitchAgent()
    return _pitch_agent
