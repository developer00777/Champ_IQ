"""Pitch Worker -- Wraps PitchAgent with model selection support.

Single Responsibility: generate pitch content (email variants + call script)
for a prospect using the PitchAgent. Supports frontend-selectable LLM model
override so users can choose which model generates their pitch content.

Key behaviours:
- Uses PitchAgent from champiq_v2.agents.pitch.agent
- If model_override is set in task_data, temporarily configures the LLM service
- Delegates all pitch generation to PitchAgent.generate()
- Returns PitchResult.to_dict()
"""

import logging
from typing import Any

from champiq_v2.config import get_settings
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


class PitchWorker(BaseWorker):
    """Pitch generation worker with frontend-selectable model support.

    Wraps PitchAgent and provides model override capability so the
    frontend can let users choose which LLM generates their pitches.
    The gateway drives all state transitions -- this worker is stateless.
    """

    worker_type = WorkerType.PITCH

    async def execute(self, task_data: dict[str, Any]) -> dict[str, Any]:
        """Generate pitch content for a prospect.

        Args:
            task_data: {
                "prospect_id": str,
                "model_override": str (optional - frontend-selected model),
                "campaign_context": str (optional),
                "variants": list[str] (default ["primary", "secondary", "nurture"]),
                "generate_call_script": bool (default True),
            }

        Returns:
            PitchResult.to_dict() -- varies by PitchAgent implementation, typically:
            {
                "emails": {
                    "primary": {"subject": str, "body": str},
                    "secondary": {"subject": str, "body": str},
                    "nurture": {"subject": str, "body": str},
                },
                "call_script": str (if generate_call_script is True),
                "model_used": str,
                "generated_at": str (ISO),
            }
        """
        prospect_id = task_data.get("prospect_id")
        if not prospect_id:
            raise PermanentError("No prospect_id provided")

        model_override = task_data.get("model_override") or ""
        campaign_context = task_data.get("campaign_context", "")
        variants = task_data.get("variants", ["primary", "secondary", "nurture"])
        generate_call_script = task_data.get("generate_call_script", True)

        # Fall back to the frontend-configured pitch model from settings
        settings = get_settings()
        effective_model = model_override or settings.pitch_model or ""

        await activity_stream.emit(ActivityEvent(
            event_type="pitch_generating",
            worker_type=self.worker_type.value,
            prospect_id=prospect_id,
            data={
                "variants": variants,
                "model_override": effective_model or "(default)",
                "generate_call_script": generate_call_script,
            },
        ))

        # If a specific model is requested, temporarily override the LLM
        llm = get_llm_service()
        old_override = llm._model_override

        try:
            if effective_model:
                llm._model_override = effective_model
                logger.info(
                    "Pitch generation using model override: %s", effective_model
                )

            # Import PitchAgent here to avoid circular imports at module level
            from champiq_v2.agents.pitch.agent import get_pitch_agent, PitchPlan

            agent = get_pitch_agent()
            plan = PitchPlan(
                prospect_id=prospect_id,
                campaign_context=campaign_context,
                email_variants=variants,
                generate_call_script=generate_call_script,
            )
            result = await agent.generate(plan)

            await activity_stream.emit(ActivityEvent(
                event_type="pitch_generated",
                worker_type=self.worker_type.value,
                prospect_id=prospect_id,
                data={
                    "variants_generated": variants,
                    "has_call_script": generate_call_script,
                    "model_used": effective_model or settings.llm_model,
                },
            ))

            return result.to_dict()

        except ImportError as e:
            logger.error("PitchAgent not available: %s", e)
            raise PermanentError(
                f"PitchAgent module not found. Ensure champiq_v2.agents.pitch.agent "
                f"is installed: {e}"
            )

        except Exception as e:
            logger.error("Pitch generation failed for prospect %s: %s", prospect_id, e)
            raise RetryableError(f"Pitch generation failed: {e}")

        finally:
            # Always restore the original model override
            llm._model_override = old_override
