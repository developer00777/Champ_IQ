"""Voice Call Worker -- ElevenLabs Conversational AI Outbound Calls.

Handles outbound voice calls using ElevenLabs Conversational AI for the
V2 fixed pipeline. Supports four agent types (qualifier, sales, nurture,
auto), each mapped to a separate ElevenLabs agent ID from config.

V2 changes from V1:
- Accepts agent_type parameter: "qualifier"|"sales"|"nurture"|"auto"
- Uses per-type ElevenLabs agent IDs from config:
    settings.elevenlabs_qualifier_agent_id
    settings.elevenlabs_sales_agent_id
    settings.elevenlabs_nurture_agent_id
    settings.elevenlabs_auto_agent_id
- Accepts context_summary in task_data, passes as dynamic_variables to ElevenLabs
- No _trigger_reevaluation or _transition_to_ready (gateway drives transitions)
- No process_callback (gateway handles webhooks)
- ActivityEvent uses V2 fields: event_type, worker_type, prospect_id, data
- Import paths use champiq_v2 everywhere
"""

import asyncio
import logging
from typing import Any, Optional

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from champiq_v2.config import get_settings
from champiq_v2.graph.service import get_graph_service
from champiq_v2.graph.entities import (
    Interaction,
    InteractionOutcome,
    InteractionType,
)
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

# ElevenLabs API endpoints
ELEVENLABS_API_BASE = "https://api.elevenlabs.io/v1"
ELEVENLABS_CONVAI_BASE = "https://api.elevenlabs.io/v1/convai"

# Valid agent types
VALID_AGENT_TYPES = {"qualifier", "sales", "nurture", "auto"}

# Map agent_type -> config attribute name for agent IDs
AGENT_ID_CONFIG_MAP: dict[str, str] = {
    "qualifier": "elevenlabs_qualifier_agent_id",
    "sales": "elevenlabs_sales_agent_id",
    "nurture": "elevenlabs_nurture_agent_id",
    "auto": "elevenlabs_auto_agent_id",
}

# Transcript polling configuration
MAX_POLL_ATTEMPTS = 12  # 12 * 10s = 2 min max (reduced from 30)
POLL_INTERVAL_SECONDS = 10


class VoiceCallWorker(BaseWorker):
    """ElevenLabs voice call worker with per-type agent selection.

    Places outbound calls via ElevenLabs Conversational AI. The agent_type
    parameter in task_data selects which ElevenLabs agent is used:

    - qualifier: CHAMP lead qualification call
    - sales: Sales qualification / closing call
    - nurture: Relationship nurture / check-in call
    - auto: Automated discovery call (no-reply follow-up)

    The gateway owns all state transitions -- this worker only places the
    call, polls for the transcript, and returns structured results.
    """

    worker_type = WorkerType.VOICE

    def __init__(self):
        super().__init__()
        self.api_key = self._get_api_key()
        self.phone_number_id = self.settings.elevenlabs_phone_number_id

    def _get_api_key(self) -> str:
        """Extract ElevenLabs API key from settings."""
        key = self.settings.elevenlabs_api_key
        if hasattr(key, "get_secret_value"):
            return key.get_secret_value()
        return str(key) if key else ""

    def _get_agent_id(self, agent_type: str) -> str:
        """Get the ElevenLabs agent ID for a given agent type from config.

        Uses per-type agent IDs:
            settings.elevenlabs_qualifier_agent_id
            settings.elevenlabs_sales_agent_id
            settings.elevenlabs_nurture_agent_id
            settings.elevenlabs_auto_agent_id
        """
        config_attr = AGENT_ID_CONFIG_MAP.get(agent_type)
        if not config_attr:
            raise PermanentError(
                f"Invalid agent_type '{agent_type}'. "
                f"Valid types: {', '.join(sorted(VALID_AGENT_TYPES))}"
            )
        agent_id = getattr(self.settings, config_attr, "")
        if not agent_id:
            raise PermanentError(
                f"ElevenLabs agent ID not configured for type '{agent_type}'. "
                f"Set {config_attr.upper()} in environment."
            )
        return agent_id

    @retry(
        retry=retry_if_exception_type(RetryableError),
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=60, max=120),
        reraise=True,
    )
    async def execute(self, task_data: dict[str, Any]) -> dict[str, Any]:
        """Place an outbound call via ElevenLabs Conversational AI.

        Args:
            task_data: {
                "prospect_id": str,
                "phone_number": str (E.164 format),
                "agent_type": str ("qualifier"|"sales"|"nurture"|"auto"),
                "context_summary": str (optional - passed as dynamic_variables),
                "prospect_name": str (optional),
                "company_name": str (optional),
            }

        Returns:
            {
                "call_id": str,
                "agent_type": str,
                "agent_id": str,
                "status": str,
                "transcript": str (if available after polling),
                "duration_seconds": int (if available),
                "started_at": str (ISO),
            }
        """
        prospect_id = task_data.get("prospect_id")
        phone_number = task_data.get("phone_number")
        agent_type = task_data.get("agent_type", "qualifier")
        context_summary = task_data.get("context_summary", "")
        prospect_name = task_data.get("prospect_name", "")
        company_name = task_data.get("company_name", "")

        if not phone_number:
            raise PermanentError("No phone_number provided")

        if not self.api_key:
            raise PermanentError(
                "ElevenLabs API key not configured. Set ELEVENLABS_API_KEY."
            )

        if agent_type not in VALID_AGENT_TYPES:
            raise PermanentError(
                f"Invalid agent_type '{agent_type}'. "
                f"Valid types: {', '.join(sorted(VALID_AGENT_TYPES))}"
            )

        agent_id = self._get_agent_id(agent_type)

        await activity_stream.emit(ActivityEvent(
            event_type="call_initiating",
            worker_type=self.worker_type.value,
            prospect_id=prospect_id,
            data={
                "phone_number": phone_number,
                "agent_type": agent_type,
                "prospect_name": prospect_name,
            },
        ))

        # Place the outbound call
        call_id = await self._initiate_elevenlabs_call(
            agent_id=agent_id,
            phone_number=phone_number,
            context_summary=context_summary,
            prospect_name=prospect_name,
            company_name=company_name,
        )

        await self._emit_call_event(
            "call_placed",
            prospect_id,
            {
                "call_id": call_id,
                "agent_type": agent_type,
                "phone_number": phone_number,
            },
        )

        # Poll for transcript
        transcript_data = await self._poll_and_process_transcript(
            call_id=call_id,
            prospect_id=prospect_id,
            agent_type=agent_type,
        )

        # Log interaction to graph
        await self._log_call_interaction(
            prospect_id=prospect_id,
            agent_type=agent_type,
            call_id=call_id,
            transcript=transcript_data.get("transcript", ""),
            duration_seconds=transcript_data.get("duration_seconds", 0),
        )

        await self._emit_call_event(
            "call_completed",
            prospect_id,
            {
                "call_id": call_id,
                "agent_type": agent_type,
                "has_transcript": bool(transcript_data.get("transcript")),
                "duration_seconds": transcript_data.get("duration_seconds", 0),
            },
        )

        return {
            "call_id": call_id,
            "agent_type": agent_type,
            "agent_id": agent_id,
            "status": transcript_data.get("status", "completed"),
            "transcript": transcript_data.get("transcript", ""),
            "duration_seconds": transcript_data.get("duration_seconds", 0),
            "started_at": now_ist().isoformat(),
        }

    # ------------------------------------------------------------------
    # ElevenLabs API interactions
    # ------------------------------------------------------------------

    async def _initiate_elevenlabs_call(
        self,
        agent_id: str,
        phone_number: str,
        context_summary: str = "",
        prospect_name: str = "",
        company_name: str = "",
    ) -> str:
        """Initiate an outbound call via ElevenLabs Conversational AI.

        If context_summary is provided, it is sent as dynamic_variables
        so the ElevenLabs agent can reference prospect context during
        the conversation.

        Returns:
            The ElevenLabs call/conversation ID.
        """
        url = f"{ELEVENLABS_CONVAI_BASE}/conversation/create-phone-call"

        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
        }

        body: dict[str, Any] = {
            "agent_id": agent_id,
            "phone_number": phone_number,
        }

        # Add phone number ID for caller ID if configured
        if self.phone_number_id:
            body["phone_number_id"] = self.phone_number_id

        # Pass context as dynamic_variables for the ElevenLabs agent
        dynamic_vars: dict[str, str] = {}
        if context_summary:
            dynamic_vars["context_summary"] = context_summary
        if prospect_name:
            dynamic_vars["prospect_name"] = prospect_name
        if company_name:
            dynamic_vars["company_name"] = company_name
        if dynamic_vars:
            body["dynamic_variables"] = dynamic_vars

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(url, headers=headers, json=body)
                response.raise_for_status()
                data = response.json()
                call_id = data.get("call_id") or data.get("conversation_id", "")

                if not call_id:
                    raise PermanentError(
                        "ElevenLabs returned no call_id or conversation_id"
                    )

                logger.info(
                    "ElevenLabs call initiated: call_id=%s, agent=%s, phone=%s",
                    call_id, agent_id, phone_number,
                )
                return call_id

            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                detail = e.response.text[:300]
                if status in (429, 500, 502, 503):
                    raise RetryableError(
                        f"ElevenLabs API error {status}: {detail}"
                    )
                raise PermanentError(
                    f"ElevenLabs API error {status}: {detail}"
                )
            except httpx.TimeoutException:
                raise RetryableError("ElevenLabs API timeout")
            except (RetryableError, PermanentError):
                raise
            except Exception as e:
                raise RetryableError(f"ElevenLabs call initiation failed: {e}")

    # ------------------------------------------------------------------
    # Transcript polling and processing
    # ------------------------------------------------------------------

    async def _poll_and_process_transcript(
        self,
        call_id: str,
        prospect_id: Optional[str],
        agent_type: str,
    ) -> dict[str, Any]:
        """Poll ElevenLabs for the call transcript until available or timeout.

        Returns:
            {
                "transcript": str,
                "duration_seconds": int,
                "status": str,
            }
        """
        if not call_id:
            return {"transcript": "", "duration_seconds": 0, "status": "no_call_id"}

        url = f"{ELEVENLABS_CONVAI_BASE}/conversation/{call_id}"
        headers = {"xi-api-key": self.api_key}

        for attempt in range(MAX_POLL_ATTEMPTS):
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    response = await client.get(url, headers=headers)
                    response.raise_for_status()
                    data = response.json()

                status = data.get("status", "unknown")

                if status in ("completed", "ended", "done"):
                    transcript = self._process_elevenlabs_transcript(data)
                    duration = data.get("duration_seconds") or data.get(
                        "metadata", {}
                    ).get("call_duration_secs", 0)
                    return {
                        "transcript": transcript,
                        "duration_seconds": int(duration),
                        "status": "completed",
                    }

                if status in ("failed", "error", "no_answer", "busy"):
                    logger.warning(
                        "Call %s ended with status: %s", call_id, status
                    )
                    return {
                        "transcript": "",
                        "duration_seconds": 0,
                        "status": status,
                    }

                # Still in progress -- emit progress event periodically
                if attempt % 3 == 0:
                    await self._emit_call_event(
                        "call_in_progress",
                        prospect_id,
                        {"call_id": call_id, "status": status, "poll_attempt": attempt},
                    )

            except httpx.HTTPStatusError as e:
                logger.debug(
                    "Poll attempt %d for call %s: HTTP %d",
                    attempt, call_id, e.response.status_code,
                )
            except Exception as e:
                logger.debug(
                    "Poll attempt %d for call %s: %s", attempt, call_id, e
                )

            await asyncio.sleep(POLL_INTERVAL_SECONDS)

        logger.warning(
            "Transcript polling timed out for call %s after %d attempts",
            call_id, MAX_POLL_ATTEMPTS,
        )
        return {"transcript": "", "duration_seconds": 0, "status": "poll_timeout"}

    @staticmethod
    def _process_elevenlabs_transcript(data: dict[str, Any]) -> str:
        """Extract and format the transcript from ElevenLabs response.

        Handles multiple response formats from different ElevenLabs API versions.
        """
        # Try direct transcript string
        transcript = data.get("transcript", "")
        if isinstance(transcript, str) and transcript.strip():
            return transcript

        # Try conversation turns format
        turns = data.get("conversation", {}).get("turns", [])
        if not turns:
            turns = data.get("turns", [])

        if isinstance(turns, list) and turns:
            parts = []
            for turn in turns:
                role = turn.get("role", "unknown")
                text = turn.get("text", "") or turn.get("message", "")
                if text:
                    label = "Agent" if role == "agent" else "Prospect"
                    parts.append(f"{label}: {text}")
            if parts:
                return "\n".join(parts)

        # Try messages format
        messages = data.get("messages", [])
        if isinstance(messages, list) and messages:
            parts = []
            for msg in messages:
                role = msg.get("role", "unknown").capitalize()
                content = msg.get("content", "") or msg.get("text", "")
                if content:
                    parts.append(f"{role}: {content}")
            if parts:
                return "\n".join(parts)

        return ""

    # ------------------------------------------------------------------
    # Interaction logging
    # ------------------------------------------------------------------

    async def _log_call_interaction(
        self,
        prospect_id: Optional[str],
        agent_type: str,
        call_id: str,
        transcript: str,
        duration_seconds: int,
    ) -> None:
        """Log the call as an interaction in the knowledge graph."""
        if not prospect_id:
            return

        try:
            graph = await get_graph_service()

            # Determine outcome based on transcript presence and duration
            if not transcript or duration_seconds < 5:
                outcome = InteractionOutcome.NO_RESPONSE
                interaction_type = InteractionType.CALL_NO_ANSWER
            else:
                outcome = InteractionOutcome.NEUTRAL
                interaction_type = InteractionType.CALL_COMPLETED

            interaction = Interaction(
                type=interaction_type,
                channel="voice",
                outcome=outcome,
                content_summary=f"[{agent_type}] ElevenLabs call ({duration_seconds}s)"[:200],
                call_duration_seconds=duration_seconds,
                transcript_summary=transcript[:500] if transcript else None,
                worker_id=call_id,
            )
            await graph.create_interaction(prospect_id, interaction)
        except Exception as e:
            logger.warning("Failed to log call interaction: %s", e)

    # ------------------------------------------------------------------
    # Event emission
    # ------------------------------------------------------------------

    async def _emit_call_event(
        self,
        event_type: str,
        prospect_id: Optional[str],
        data: dict[str, Any],
    ) -> None:
        """Emit a call-related activity event to the gateway."""
        await activity_stream.emit(ActivityEvent(
            event_type=event_type,
            worker_type=self.worker_type.value,
            prospect_id=prospect_id,
            data=data,
        ))
