"""Settings API routes - read and update runtime configuration."""

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, SecretStr

from champiq_v2.api.dependencies import verify_internal_secret
from champiq_v2.config import get_settings

router = APIRouter(tags=["Settings"], dependencies=[Depends(verify_internal_secret)])


class SmtpSettings(BaseModel):
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    smtp_from_email: str
    smtp_from_name: str
    smtp_use_tls: bool


class ImapSettings(BaseModel):
    imap_host: str
    imap_port: int
    imap_user: str
    imap_password: str
    imap_use_ssl: bool


class VoiceSettings(BaseModel):
    elevenlabs_qualifier_agent_id: str
    elevenlabs_sales_agent_id: str
    elevenlabs_nurture_agent_id: str
    elevenlabs_auto_agent_id: str


class PipelineSettings(BaseModel):
    imap_wait_hours: int
    pitch_model: str


class SettingsUpdateRequest(BaseModel):
    smtp: Optional[SmtpSettings] = None
    imap: Optional[ImapSettings] = None
    voice: Optional[VoiceSettings] = None
    pipeline: Optional[PipelineSettings] = None


class SettingsResponse(BaseModel):
    smtp: SmtpSettings
    imap: ImapSettings
    voice: VoiceSettings
    pipeline: PipelineSettings


def _mask(secret: SecretStr) -> str:
    v = secret.get_secret_value() if secret else ""
    return "••••••••" if v else ""


@router.get("/settings", response_model=SettingsResponse)
async def get_runtime_settings() -> SettingsResponse:
    """Return current runtime settings (passwords masked)."""
    s = get_settings()
    return SettingsResponse(
        smtp=SmtpSettings(
            smtp_host=s.smtp_host,
            smtp_port=s.smtp_port,
            smtp_user=s.smtp_user,
            smtp_password=_mask(s.smtp_password),
            smtp_from_email=s.smtp_from_email,
            smtp_from_name=s.smtp_from_name,
            smtp_use_tls=s.smtp_use_tls,
        ),
        imap=ImapSettings(
            imap_host=s.imap_host,
            imap_port=s.imap_port,
            imap_user=s.imap_user,
            imap_password=_mask(s.imap_password),
            imap_use_ssl=s.imap_use_ssl,
        ),
        voice=VoiceSettings(
            elevenlabs_qualifier_agent_id=s.elevenlabs_qualifier_agent_id,
            elevenlabs_sales_agent_id=s.elevenlabs_sales_agent_id,
            elevenlabs_nurture_agent_id=s.elevenlabs_nurture_agent_id,
            elevenlabs_auto_agent_id=s.elevenlabs_auto_agent_id,
        ),
        pipeline=PipelineSettings(
            imap_wait_hours=s.imap_wait_hours,
            pitch_model=s.pitch_model,
        ),
    )


@router.post("/settings", response_model=SettingsResponse)
async def update_runtime_settings(payload: SettingsUpdateRequest) -> SettingsResponse:
    """Update runtime settings in-memory (not persisted to .env)."""
    s = get_settings()

    if payload.smtp:
        s.smtp_host = payload.smtp.smtp_host
        s.smtp_port = payload.smtp.smtp_port
        s.smtp_user = payload.smtp.smtp_user
        if payload.smtp.smtp_password and payload.smtp.smtp_password != "••••••••":
            s.smtp_password = SecretStr(payload.smtp.smtp_password)
        s.smtp_from_email = payload.smtp.smtp_from_email
        s.smtp_from_name = payload.smtp.smtp_from_name
        s.smtp_use_tls = payload.smtp.smtp_use_tls

    if payload.imap:
        s.imap_host = payload.imap.imap_host
        s.imap_port = payload.imap.imap_port
        s.imap_user = payload.imap.imap_user
        if payload.imap.imap_password and payload.imap.imap_password != "••••••••":
            s.imap_password = SecretStr(payload.imap.imap_password)
        s.imap_use_ssl = payload.imap.imap_use_ssl

    if payload.voice:
        s.elevenlabs_qualifier_agent_id = payload.voice.elevenlabs_qualifier_agent_id
        s.elevenlabs_sales_agent_id = payload.voice.elevenlabs_sales_agent_id
        s.elevenlabs_nurture_agent_id = payload.voice.elevenlabs_nurture_agent_id
        s.elevenlabs_auto_agent_id = payload.voice.elevenlabs_auto_agent_id

    if payload.pipeline:
        s.imap_wait_hours = payload.pipeline.imap_wait_hours
        s.pitch_model = payload.pipeline.pitch_model

    return await get_runtime_settings()
