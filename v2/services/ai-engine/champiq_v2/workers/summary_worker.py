"""Summary Worker -- Transcript to LLM summary with graph persistence.

Single Responsibility: take a call transcript, generate a structured LLM
summary, extract CHAMP signals, and save everything to the knowledge graph
via GraphService.save_call_summary().

Used after every voice call (qualifier, sales, nurture, auto) to produce
structured summaries that feed back into the prospect context.
"""

import json
import logging
from typing import Any

from champiq_v2.config import get_settings
from champiq_v2.graph.service import get_graph_service
from champiq_v2.llm.service import get_llm_service
from champiq_v2.workers.base import (
    BaseWorker,
    PermanentError,
    RetryableError,
    WorkerType,
    activity_stream,
    ActivityEvent,
)
from champiq_v2.utils.timezone import now_ist

logger = logging.getLogger(__name__)

# System prompt for transcript summarisation
SUMMARY_SYSTEM_PROMPT = """\
You are an expert B2B sales analyst. You analyse call transcripts and extract
structured insights that help sales teams qualify leads and plan next steps.
Always return valid JSON."""

# CHAMP signal extraction prompt template
CHAMP_EXTRACTION_PROMPT = """\
Analyse the following {call_type} call transcript and extract CHAMP qualification signals.

CHAMP framework:
- Challenges: What business challenges/pain points did the prospect mention?
- Authority: Does this person have decision-making power? Who else is involved?
- Money: Any mention of budget, spending, cost concerns, or ROI expectations?
- Prioritisation: How urgent is solving this problem? Timeline mentioned?

Transcript:
{transcript}

Return a JSON object:
{{
    "summary": "2-3 sentence summary of the call",
    "champ_signals": {{
        "challenges": {{
            "score": 0-100,
            "evidence": ["quote or observation 1", "quote 2"],
            "notes": "brief analysis"
        }},
        "authority": {{
            "score": 0-100,
            "evidence": ["quote or observation 1"],
            "notes": "brief analysis"
        }},
        "money": {{
            "score": 0-100,
            "evidence": ["quote or observation 1"],
            "notes": "brief analysis"
        }},
        "prioritisation": {{
            "score": 0-100,
            "evidence": ["quote or observation 1"],
            "notes": "brief analysis"
        }}
    }},
    "interested": true/false,
    "sentiment": "positive"|"neutral"|"negative",
    "key_points": ["key point 1", "key point 2"],
    "objections": ["objection 1"],
    "next_steps": ["recommended next step 1"]
}}"""


class SummaryWorker(BaseWorker):
    """Transcript summarisation worker with CHAMP signal extraction.

    Processes call transcripts through the LLM to produce:
    1. A structured summary of the conversation
    2. CHAMP qualification signals (challenges, authority, money, prioritisation)
    3. Sentiment analysis and interest determination

    Saves the summary to the knowledge graph via GraphService.save_call_summary().
    """

    worker_type = WorkerType.SUMMARY

    async def execute(self, task_data: dict[str, Any]) -> dict[str, Any]:
        """Summarise a call transcript and save to graph.

        Args:
            task_data: {
                "prospect_id": str,
                "transcript": str,
                "call_type": str ("qualifier"|"sales"|"nurture"|"auto"),
            }

        Returns:
            {
                "summary": str,
                "champ_signals": {
                    "challenges": {"score": int, "evidence": list, "notes": str},
                    "authority": {"score": int, "evidence": list, "notes": str},
                    "money": {"score": int, "evidence": list, "notes": str},
                    "prioritisation": {"score": int, "evidence": list, "notes": str},
                },
                "interested": bool,
                "sentiment": str,
                "key_points": list[str],
                "objections": list[str],
                "next_steps": list[str],
            }
        """
        prospect_id = task_data.get("prospect_id")
        transcript = task_data.get("transcript", "")
        call_type = task_data.get("call_type", "qualifier")

        if not prospect_id:
            raise PermanentError("No prospect_id provided")

        if not transcript or not transcript.strip():
            logger.warning(
                "Empty transcript for prospect %s, returning minimal summary",
                prospect_id,
            )
            return self._empty_result(call_type)

        await activity_stream.emit(ActivityEvent(
            event_type="summary_generating",
            worker_type=self.worker_type.value,
            prospect_id=prospect_id,
            data={"call_type": call_type, "transcript_length": len(transcript)},
        ))

        # Step 1: Use LLM to summarise transcript and extract CHAMP signals
        llm = get_llm_service()
        analysis = await self._analyse_transcript(llm, transcript, call_type)

        summary_text = analysis.get("summary", transcript[:200])
        champ_signals = analysis.get("champ_signals", self._empty_champ_signals())

        # Step 2: Save summary to graph via GraphService.save_call_summary()
        try:
            graph = await get_graph_service()
            await graph.save_call_summary(
                prospect_id=prospect_id,
                call_type=call_type,
                summary=summary_text,
                transcript=transcript,
            )
            logger.info(
                "Call summary saved to graph for prospect %s (%s call)",
                prospect_id, call_type,
            )
        except Exception as e:
            logger.warning("Failed to save call summary to graph: %s", e)

        await activity_stream.emit(ActivityEvent(
            event_type="summary_generated",
            worker_type=self.worker_type.value,
            prospect_id=prospect_id,
            data={
                "call_type": call_type,
                "interested": analysis.get("interested", False),
                "sentiment": analysis.get("sentiment", "neutral"),
            },
        ))

        return {
            "summary": summary_text,
            "champ_signals": champ_signals,
            "interested": analysis.get("interested", False),
            "sentiment": analysis.get("sentiment", "neutral"),
            "key_points": analysis.get("key_points", []),
            "objections": analysis.get("objections", []),
            "next_steps": analysis.get("next_steps", []),
        }

    # ------------------------------------------------------------------
    # LLM analysis
    # ------------------------------------------------------------------

    async def _analyse_transcript(
        self, llm: Any, transcript: str, call_type: str
    ) -> dict[str, Any]:
        """Use LLM to analyse the transcript and extract structured data."""
        prompt = CHAMP_EXTRACTION_PROMPT.format(
            call_type=call_type,
            transcript=transcript[:6000],  # Truncate very long transcripts
        )

        try:
            result = await llm.complete_json(
                prompt=prompt,
                system_prompt=SUMMARY_SYSTEM_PROMPT,
            )
            # Validate expected structure
            if not isinstance(result, dict):
                raise ValueError(f"Expected dict, got {type(result)}")
            return result

        except Exception as e:
            logger.warning(
                "LLM transcript analysis failed, using basic summarisation: %s", e
            )
            # Fall back to the simpler summarize_transcript method (returns str)
            try:
                basic_summary = await llm.summarize_transcript(transcript, call_type)
                return {
                    "summary": basic_summary,
                    "champ_signals": self._empty_champ_signals(),
                    "interested": False,
                    "sentiment": "neutral",
                    "key_points": [],
                    "objections": [],
                    "next_steps": [],
                }
            except Exception as e2:
                logger.warning("Fallback summarisation also failed: %s", e2)
                return {
                    "summary": transcript[:200],
                    "champ_signals": self._empty_champ_signals(),
                    "interested": False,
                    "sentiment": "neutral",
                    "key_points": [],
                    "objections": [],
                    "next_steps": [],
                }

    # ------------------------------------------------------------------
    # Defaults / empty results
    # ------------------------------------------------------------------

    @staticmethod
    def _empty_champ_signals() -> dict[str, Any]:
        """Return an empty CHAMP signals structure."""
        empty_dimension = {"score": 0, "evidence": [], "notes": "No data available"}
        return {
            "challenges": dict(empty_dimension),
            "authority": dict(empty_dimension),
            "money": dict(empty_dimension),
            "prioritisation": dict(empty_dimension),
        }

    def _empty_result(self, call_type: str) -> dict[str, Any]:
        """Return a minimal result for empty transcripts."""
        return {
            "summary": f"Empty transcript for {call_type} call.",
            "champ_signals": self._empty_champ_signals(),
            "interested": False,
            "sentiment": "neutral",
            "key_points": [],
            "objections": [],
            "next_steps": [],
        }
