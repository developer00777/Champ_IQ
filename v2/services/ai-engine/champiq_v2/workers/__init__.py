"""ChampIQ V2 AI Engine Workers.

Provides all worker implementations for the V2 fixed pipeline:
- SMTPEmailWorker: Email sending with availability CTA
- VoiceCallWorker: ElevenLabs voice calls with agent type selection
- ResearchWorker: Perplexity Sonar research + Graphiti ingestion
- IMAPWorker: Standalone IMAP reply checker
- PitchWorker: Pitch generation with frontend-selectable model
- SummaryWorker: Transcript summarization + graph persistence
- ContextBuilder: Assembles full prospect context for ElevenLabs agents
"""

from champiq_v2.workers.base import (
    BaseWorker,
    WorkerResult,
    WorkerStatus,
    WorkerType,
    WorkerRegistry,
    ActivityStream,
    ActivityEvent,
    activity_stream,
    RetryableError,
    PermanentError,
)
from champiq_v2.workers.smtp_worker import SMTPEmailWorker
from champiq_v2.workers.voice_worker import VoiceCallWorker
from champiq_v2.workers.research_worker import ResearchWorker
from champiq_v2.workers.imap_worker import IMAPWorker
from champiq_v2.workers.pitch_worker import PitchWorker
from champiq_v2.workers.summary_worker import SummaryWorker
from champiq_v2.workers.context_builder import ContextBuilder


def register_all_workers():
    """Register all built-in workers with the WorkerRegistry."""
    WorkerRegistry.register(SMTPEmailWorker())
    WorkerRegistry.register(VoiceCallWorker())
    WorkerRegistry.register(ResearchWorker())
    WorkerRegistry.register(IMAPWorker())
    WorkerRegistry.register(PitchWorker())
    WorkerRegistry.register(SummaryWorker())
    WorkerRegistry.register(ContextBuilder())
