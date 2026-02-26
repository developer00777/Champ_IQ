"""SMTP Email Worker -- Sends emails with availability CTA.

Handles all outbound email operations for the V2 pipeline:
- Initial pitch emails (with availability CTA appended)
- Follow-up emails (reuses execute() with variant="follow_up")
- Email content generation via LLM
- SMTP sending (real or simulated)
- Interaction logging to the knowledge graph

V2 changes from V1:
- No wait_for_reply or check_responses (IMAP is a separate worker)
- No IMAP-related init params or logic
- All emails include availability CTA: "Would [time] work for a quick 15-minute call?"
- send_followup() reuses execute() with variant="follow_up"
- No _trigger_reevaluation or _transition_to_ready (gateway drives transitions)
- ActivityEvent uses V2 fields: event_type, worker_type, prospect_id, data
- Import paths use champiq_v2 everywhere
"""

import email.mime.multipart
import email.mime.text
import json
import logging
import re
import uuid
from typing import Any, Optional
from urllib.parse import urlencode, urlparse, urlunparse, parse_qs

import aiosmtplib
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from champiq_v2.config import get_settings
from champiq_v2.graph.service import get_graph_service
from champiq_v2.graph.entities import Interaction, InteractionOutcome, InteractionType
from champiq_v2.llm.service import get_llm_service
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

# Availability CTA appended to every outbound email
AVAILABILITY_CTA = (
    "\n\nWould [morning/afternoon this week] work for a quick 15-minute call? "
    "Just reply with your availability and I'll send over a calendar invite."
)

# Follow-up specific CTA
FOLLOWUP_AVAILABILITY_CTA = (
    "\n\nWould [Tuesday or Thursday] work for a quick 15-minute call? "
    "Happy to work around your schedule."
)


class SMTPEmailWorker(BaseWorker):
    """SMTP email worker with availability CTA and follow-up support.

    All outbound emails automatically append an availability CTA asking
    the prospect for a 15-minute call slot. The gateway drives all state
    transitions -- this worker is stateless.

    Supports:
    - Initial pitch emails (variant="primary"|"secondary"|"nurture")
    - Follow-up emails (variant="follow_up") via send_followup()
    - Auto-generated or pre-supplied email content
    - UTM tracking link injection
    - HTML email conversion
    """

    worker_type = WorkerType.EMAIL

    def __init__(self):
        super().__init__()
        self.smtp_host = self.settings.smtp_host
        self.smtp_port = self.settings.smtp_port
        self.smtp_user = self.settings.smtp_user
        self.smtp_password = self._get_smtp_password()
        self.smtp_use_tls = self.settings.smtp_use_tls
        self.from_email = self.settings.smtp_from_email
        self.from_name = self.settings.smtp_from_name

    def _get_smtp_password(self) -> str:
        """Extract SMTP password from settings (handles SecretStr)."""
        pwd = self.settings.smtp_password
        if hasattr(pwd, "get_secret_value"):
            return pwd.get_secret_value()
        return str(pwd) if pwd else ""

    @property
    def is_smtp_configured(self) -> bool:
        """Check if SMTP is configured for real sending."""
        return bool(self.smtp_host and self.smtp_user and self.smtp_password)

    @retry(
        retry=retry_if_exception_type(RetryableError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=30, max=120),
        reraise=True,
    )
    async def execute(self, task_data: dict[str, Any]) -> dict[str, Any]:
        """Send a pitch email to a prospect with availability CTA.

        Args:
            task_data: {
                "prospect_id": str,
                "to_email": str,
                "to_name": str (optional),
                "subject": str (optional - auto-generated if missing),
                "body": str (optional - auto-generated if missing),
                "variant": str (optional, default "primary"),
                "campaign_context": str (optional),
                "campaign_id": str (optional, for UTM tracking),
            }

        Returns:
            {
                "message_id": str,
                "sent_at": str (ISO),
                "subject": str,
                "variant": str,
                "to_email": str,
                "simulated": bool,
            }
        """
        prospect_id = task_data.get("prospect_id")
        to_email = task_data.get("to_email")
        to_name = task_data.get("to_name", "")
        variant = task_data.get("variant", "primary")

        if not to_email:
            raise PermanentError("No to_email provided")

        # Generate or use provided content
        subject = task_data.get("subject")
        body = task_data.get("body")

        if not subject or not body:
            generated = await self._generate_email_content(
                prospect_id=prospect_id,
                to_name=to_name,
                variant=variant,
                campaign_context=task_data.get("campaign_context"),
            )
            subject = subject or generated.get("subject", self._get_fallback_subject(to_name, variant))
            body = body or generated.get("body", self._get_fallback_email(to_name, variant))

        # Append availability CTA to every email
        if variant == "follow_up":
            body = body.rstrip() + FOLLOWUP_AVAILABILITY_CTA
        else:
            body = body.rstrip() + AVAILABILITY_CTA

        # Add UTM tracking to any links
        campaign_id = task_data.get("campaign_id")
        if campaign_id:
            body = self._add_utm_tracking(body, campaign_id, variant)

        await activity_stream.emit(ActivityEvent(
            event_type="email_sending",
            worker_type=self.worker_type.value,
            prospect_id=prospect_id,
            data={"to_email": to_email, "variant": variant},
        ))

        message_id, simulated = await self._send_email(to_email, to_name, subject, body)

        await self._log_interaction(prospect_id, subject, variant, body)

        await activity_stream.emit(ActivityEvent(
            event_type="email_sent",
            worker_type=self.worker_type.value,
            prospect_id=prospect_id,
            data={
                "to_email": to_email,
                "subject": subject,
                "message_id": message_id,
                "simulated": simulated,
            },
        ))

        return {
            "message_id": message_id,
            "sent_at": now_ist().isoformat(),
            "subject": subject,
            "variant": variant,
            "to_email": to_email,
            "simulated": simulated,
        }

    async def send_followup(self, task_data: dict[str, Any]) -> dict[str, Any]:
        """Send a follow-up email -- reuses execute() with variant="follow_up".

        Accepts all the same task_data fields as execute(), plus:
            "original_subject": str (optional) - prefixed with "Re: " for threading

        Returns:
            Same as execute().
        """
        original_subject = task_data.get("original_subject", "")
        to_name = task_data.get("to_name", "")

        followup_data = dict(task_data)
        followup_data["variant"] = "follow_up"

        # Generate follow-up subject if not provided
        if not followup_data.get("subject"):
            if original_subject:
                followup_data["subject"] = f"Re: {original_subject}"
            else:
                followup_data["subject"] = f"Following up, {to_name or 'there'}"

        # Generate follow-up body if not provided
        if not followup_data.get("body"):
            followup_data["body"] = self._get_followup_body(to_name)

        return await self.execute(followup_data)

    # ------------------------------------------------------------------
    # Email content generation
    # ------------------------------------------------------------------

    async def _generate_email_content(
        self,
        prospect_id: Optional[str],
        to_name: str,
        variant: str,
        campaign_context: Optional[str] = None,
    ) -> dict[str, str]:
        """Generate email subject and body using LLM and prospect context."""
        try:
            llm = get_llm_service()
            graph = await get_graph_service()

            # Build prospect context for personalization
            prospect_context: dict[str, Any] = {}
            if prospect_id:
                try:
                    ctx = await graph.get_prospect_context(prospect_id)
                    if ctx:
                        prospect_context["prospect"] = {
                            "name": ctx.prospect.name,
                            "title": ctx.prospect.title,
                            "email": ctx.prospect.email,
                        }
                        if ctx.company:
                            prospect_context["company"] = {
                                "name": ctx.company.name,
                                "industry": ctx.company.industry,
                                "employee_count_range": ctx.company.employee_count_range,
                                "recent_news": ctx.company.recent_news[:3] if ctx.company.recent_news else [],
                            }
                        if ctx.pain_points:
                            prospect_context["pain_points"] = [
                                {"category": pp.category.value, "description": pp.description}
                                for pp in ctx.pain_points[:5]
                            ]
                except Exception as e:
                    logger.debug("Could not get prospect context: %s", e)

            if campaign_context:
                prospect_context["campaign_context"] = campaign_context

            result = await llm.generate_email(prospect_context, variant=variant)
            return {
                "subject": result.get("subject", self._get_fallback_subject(to_name, variant)),
                "body": result.get("body", self._get_fallback_email(to_name, variant)),
            }

        except Exception as e:
            logger.warning("Email content generation failed: %s", e)
            return {
                "subject": self._get_fallback_subject(to_name, variant),
                "body": self._get_fallback_email(to_name, variant),
            }

    # ------------------------------------------------------------------
    # SMTP sending
    # ------------------------------------------------------------------

    async def _send_email(
        self, to_email: str, to_name: str, subject: str, body: str
    ) -> tuple[str, bool]:
        """Send an email via SMTP or simulate if not configured.

        Returns:
            Tuple of (message_id, simulated).
        """
        message_id = f"<{uuid.uuid4()}@champiq.local>"

        if not self.is_smtp_configured:
            logger.info(
                "Simulating email send to %s: %s", to_email, subject
            )
            return message_id, True

        # Build MIME message
        msg = email.mime.multipart.MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{self.from_name} <{self.from_email}>"
        msg["To"] = f"{to_name} <{to_email}>" if to_name else to_email
        msg["Message-ID"] = message_id

        # Plain text part
        msg.attach(email.mime.text.MIMEText(body, "plain"))

        # HTML part
        html_body = self._convert_to_html(body)
        msg.attach(email.mime.text.MIMEText(html_body, "html"))

        await self._smtp_send_async(to_email, msg)
        return message_id, False

    async def _smtp_send_async(
        self,
        to_email: str,
        msg: email.mime.multipart.MIMEMultipart,
    ) -> None:
        """Native async SMTP send via aiosmtplib."""
        try:
            await aiosmtplib.send(
                msg,
                hostname=self.smtp_host,
                port=self.smtp_port,
                username=self.smtp_user,
                password=self.smtp_password,
                start_tls=self.smtp_use_tls,
                timeout=30,
            )
            logger.info("Email sent to %s", to_email)
        except aiosmtplib.SMTPAuthenticationError as e:
            raise PermanentError(f"SMTP authentication failed: {e}")
        except aiosmtplib.SMTPException as e:
            raise RetryableError(f"SMTP error: {e}")
        except Exception as e:
            raise RetryableError(f"Email send failed: {e}")

    # ------------------------------------------------------------------
    # Interaction logging
    # ------------------------------------------------------------------

    async def _log_interaction(
        self,
        prospect_id: Optional[str],
        subject: str,
        variant: str,
        body: Optional[str],
    ) -> None:
        """Log the email as an interaction in the knowledge graph."""
        if not prospect_id:
            return

        try:
            graph = await get_graph_service()
            interaction = Interaction(
                type=InteractionType.EMAIL_SENT,
                channel="email",
                outcome=InteractionOutcome.NEUTRAL,
                content_summary=f"[{variant}] {subject}"[:200],
                raw_content=body[:2000] if body else None,
            )
            await graph.create_interaction(prospect_id, interaction)
        except Exception as e:
            logger.warning("Failed to log email interaction: %s", e)

    # ------------------------------------------------------------------
    # HTML conversion
    # ------------------------------------------------------------------

    @staticmethod
    def _convert_to_html(body: str) -> str:
        """Convert plain text email body to basic HTML."""
        # Escape HTML entities
        escaped = (
            body.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        # Convert double newlines to paragraphs
        paragraphs = escaped.split("\n\n")
        html_parts = [f"<p>{p.replace(chr(10), '<br>')}</p>" for p in paragraphs]
        return (
            '<!DOCTYPE html>\n'
            '<html>\n'
            '<head><meta charset="utf-8"></head>\n'
            '<body style="font-family: Arial, sans-serif; font-size: 14px; '
            'line-height: 1.6; color: #333;">\n'
            f'{"".join(html_parts)}\n'
            '</body>\n'
            '</html>'
        )

    # ------------------------------------------------------------------
    # UTM tracking
    # ------------------------------------------------------------------

    @staticmethod
    def _add_utm_tracking(body: str, campaign_id: str, variant: str) -> str:
        """Append UTM parameters to any URLs found in the email body."""
        utm_params = {
            "utm_source": "champiq",
            "utm_medium": "email",
            "utm_campaign": campaign_id,
            "utm_content": variant,
        }

        url_pattern = re.compile(r'(https?://[^\s\)<>"]+)')

        def _add_params(match: re.Match) -> str:
            url = match.group(1)
            parsed = urlparse(url)
            existing = parse_qs(parsed.query)
            existing.update(utm_params)
            new_query = urlencode(existing, doseq=True)
            return urlunparse(parsed._replace(query=new_query))

        return url_pattern.sub(_add_params, body)

    # ------------------------------------------------------------------
    # Fallback content
    # ------------------------------------------------------------------

    @staticmethod
    def _get_fallback_subject(to_name: str, variant: str) -> str:
        """Return a fallback subject line when LLM generation fails."""
        name = to_name or "there"
        if variant == "follow_up":
            return f"Following up, {name}"
        if variant == "nurture":
            return f"Thought you'd find this interesting, {name}"
        return f"Quick question, {name}"

    def _get_fallback_email(self, to_name: str, variant: str) -> str:
        """Return a fallback email body when LLM generation fails."""
        name = to_name or "there"
        if variant == "follow_up":
            return self._get_followup_body(name)
        return (
            f"Hi {name},\n\n"
            f"I came across your profile and thought we might be able to help "
            f"with your outreach efforts. We work with companies like yours to "
            f"improve lead quality and conversion rates.\n\n"
            f"Best,\n{self.from_name}"
        )

    def _get_followup_body(self, to_name: str) -> str:
        """Generate a follow-up email body."""
        name = to_name or "there"
        return (
            f"Hi {name},\n\n"
            f"I wanted to follow up on my previous email. I understand you're "
            f"busy -- just wanted to check if you had a chance to look at it.\n\n"
            f"If this isn't the right time, no worries at all. But if you're "
            f"open to a quick conversation, I think it could be valuable.\n\n"
            f"Best,\n{self.from_name}"
        )
