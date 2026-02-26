"""IMAP Reply Checker Worker -- Standalone inbox reply checker.

Single Responsibility: check an IMAP inbox for a reply from a specific
prospect email address. Returns reply data if found.

This is a standalone worker in V2 -- the V1 IMAP logic was embedded in
the SMTP worker. In V2, the gateway drives the timing of IMAP checks
via BullMQ scheduling. This worker performs a single check and returns.

Key behaviours:
- Single check by default (no polling -- gateway handles wait timing)
- Uses imaplib for sync IMAP, run in executor for async compatibility
- Extracts reply text from multipart emails
- Uses IMAP settings from config (imap_host, imap_port, etc.)
"""

import asyncio
import email as email_lib
import email.header
import email.utils
import imaplib
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from champiq_v2.config import get_settings
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


class IMAPWorker(BaseWorker):
    """Standalone IMAP reply checker -- Single Responsibility.

    Checks the configured IMAP inbox for emails from a specific prospect.
    Does NOT handle any pipeline logic, scheduling, or state transitions.
    The gateway drives all timing and transitions.
    """

    worker_type = WorkerType.IMAP

    def __init__(self):
        super().__init__()
        self.imap_host = self.settings.imap_host
        self.imap_port = self.settings.imap_port
        self.imap_user = self.settings.imap_user
        self.imap_password = self._get_imap_password()
        self.imap_use_ssl = self.settings.imap_use_ssl

    def _get_imap_password(self) -> str:
        """Extract IMAP password from settings (handles SecretStr)."""
        pwd = self.settings.imap_password
        if hasattr(pwd, "get_secret_value"):
            return pwd.get_secret_value()
        return str(pwd) if pwd else ""

    @property
    def is_imap_configured(self) -> bool:
        """Check if IMAP is configured for real inbox checking."""
        return bool(self.imap_host and self.imap_user and self.imap_password)

    async def execute(self, task_data: dict[str, Any]) -> dict[str, Any]:
        """Check IMAP inbox for a reply from a specific prospect.

        Performs a single check (no polling). The gateway handles wait
        timing and scheduling repeated checks.

        Args:
            task_data: {
                "prospect_id": str,
                "prospect_email": str,
                "email_sent_at": str (optional ISO datetime - SINCE filter anchor),
                "since_message_id": str (optional - filter replies after this message),
                "timeout_minutes": int (default 0 = single check, no polling),
            }

        Returns:
            {
                "replied": bool,
                "reply_subject": str,
                "reply_body": str,
                "reply_date": str,
            }
        """
        prospect_id = task_data.get("prospect_id")
        prospect_email = task_data.get("prospect_email")
        email_sent_at = task_data.get("email_sent_at")
        since_message_id = task_data.get("since_message_id", "")
        timeout_minutes = task_data.get("timeout_minutes", 0)

        # Compute SINCE date: 1 day before email_sent_at to catch same-day replies
        since_date: Optional[datetime] = None
        if email_sent_at:
            try:
                from datetime import timezone as _tz
                sent_dt = datetime.fromisoformat(email_sent_at.replace("Z", "+00:00"))
                since_date = sent_dt - timedelta(days=1)
            except (ValueError, AttributeError):
                logger.debug("Could not parse email_sent_at: %s", email_sent_at)

        if not prospect_email:
            raise PermanentError("No prospect_email provided")

        if not self.is_imap_configured:
            logger.warning("IMAP not configured -- returning no reply")
            return {
                "replied": False,
                "reply_subject": "",
                "reply_body": "",
                "reply_date": "",
            }

        await activity_stream.emit(ActivityEvent(
            event_type="imap_checking",
            worker_type=self.worker_type.value,
            prospect_id=prospect_id,
            data={"prospect_email": prospect_email},
        ))

        # Single check (default) or timed polling
        if timeout_minutes <= 0:
            reply = await self._check_once(prospect_email, since_message_id, since_date)
        else:
            reply = await self._check_with_timeout(
                prospect_email, since_message_id, timeout_minutes, since_date
            )

        replied = reply is not None

        await activity_stream.emit(ActivityEvent(
            event_type="imap_checked",
            worker_type=self.worker_type.value,
            prospect_id=prospect_id,
            data={"replied": replied, "prospect_email": prospect_email},
        ))

        if reply:
            return {
                "replied": True,
                "reply_subject": reply.get("subject", ""),
                "reply_body": reply.get("body", ""),
                "reply_date": reply.get("date", ""),
            }

        return {
            "replied": False,
            "reply_subject": "",
            "reply_body": "",
            "reply_date": "",
        }

    # ------------------------------------------------------------------
    # IMAP checking (single + timed)
    # ------------------------------------------------------------------

    async def _check_once(
        self,
        prospect_email: str,
        since_message_id: str = "",
        since_date: Optional[datetime] = None,
    ) -> Optional[dict[str, str]]:
        """Perform a single IMAP check. Run sync IMAP in executor."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._imap_check_sync, prospect_email, since_message_id, since_date
        )

    async def _check_with_timeout(
        self,
        prospect_email: str,
        since_message_id: str,
        timeout_minutes: int,
        since_date: Optional[datetime] = None,
    ) -> Optional[dict[str, str]]:
        """Poll IMAP at intervals until reply found or timeout.

        This is rarely used -- the gateway normally schedules individual
        single checks. But available for backwards compatibility.
        """
        interval_seconds = 60  # Check every minute
        max_checks = timeout_minutes  # One check per minute

        for i in range(max_checks):
            reply = await self._check_once(prospect_email, since_message_id, since_date)
            if reply:
                return reply
            if i < max_checks - 1:
                await asyncio.sleep(interval_seconds)

        return None

    # ------------------------------------------------------------------
    # Synchronous IMAP operations (run in executor)
    # ------------------------------------------------------------------

    def _imap_check_sync(
        self,
        from_email: str,
        since_message_id: str = "",
        since_date: Optional[datetime] = None,
    ) -> Optional[dict[str, str]]:
        """Synchronous IMAP check for a reply from a specific sender.

        Uses imaplib to connect, search for messages from the prospect
        email, and extract the most recent reply text.

        If since_date is provided, adds an IMAP SINCE criterion to avoid
        scanning the entire inbox — only emails received on/after that date.
        """
        mail: Optional[imaplib.IMAP4] = None
        try:
            # Connect to IMAP server
            if self.imap_use_ssl:
                mail = imaplib.IMAP4_SSL(self.imap_host, self.imap_port)
            else:
                mail = imaplib.IMAP4(self.imap_host, self.imap_port)

            mail.login(self.imap_user, self.imap_password)
            mail.select("INBOX")

            # Build search criteria — filter by sender and optionally by date
            if since_date:
                # IMAP SINCE format: DD-Mon-YYYY (e.g. "01-Jan-2024")
                since_str = since_date.strftime("%d-%b-%Y")
                search_criteria = f'SINCE "{since_str}" FROM "{from_email}"'
            else:
                search_criteria = f'FROM "{from_email}"'
            _, message_numbers = mail.search(None, search_criteria)

            if not message_numbers or not message_numbers[0]:
                mail.logout()
                return None

            nums = message_numbers[0].split()
            if not nums:
                mail.logout()
                return None

            # Fetch the most recent email from this sender
            latest_num = nums[-1]
            _, msg_data = mail.fetch(latest_num, "(RFC822)")

            if not msg_data or not msg_data[0] or not msg_data[0][1]:
                mail.logout()
                return None

            raw_email = msg_data[0][1]
            msg = email_lib.message_from_bytes(raw_email)

            # Extract reply content
            subject = self._decode_header(msg.get("Subject", ""))
            date_str = msg.get("Date", "")
            body = self._extract_reply_text(msg)

            mail.logout()

            return {
                "subject": subject,
                "body": body,
                "date": date_str,
                "from": msg.get("From", ""),
            }

        except imaplib.IMAP4.error as e:
            logger.error("IMAP protocol error: %s", e)
            return None
        except Exception as e:
            logger.error("IMAP check failed: %s", e)
            return None
        finally:
            if mail:
                try:
                    mail.logout()
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Email parsing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_reply_text(msg: email_lib.message.Message) -> str:
        """Extract reply text from a multipart or plain email message.

        For multipart messages, prefers text/plain over text/html.
        Truncates to a reasonable length for storage.
        """
        max_length = 2000

        if msg.is_multipart():
            # Walk through parts, prefer text/plain
            plain_parts: list[str] = []
            html_parts: list[str] = []

            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", ""))

                # Skip attachments
                if "attachment" in content_disposition:
                    continue

                try:
                    payload = part.get_payload(decode=True)
                    if not payload:
                        continue

                    charset = part.get_content_charset() or "utf-8"
                    text = payload.decode(charset, errors="replace")

                    if content_type == "text/plain":
                        plain_parts.append(text)
                    elif content_type == "text/html":
                        html_parts.append(text)
                except Exception:
                    continue

            # Prefer plain text
            if plain_parts:
                return "\n".join(plain_parts)[:max_length]
            if html_parts:
                # Basic HTML stripping
                import re
                html = "\n".join(html_parts)
                text = re.sub(r"<[^>]+>", " ", html)
                text = re.sub(r"\s+", " ", text).strip()
                return text[:max_length]

            return ""

        else:
            # Single part message
            try:
                payload = msg.get_payload(decode=True)
                if not payload:
                    return ""
                charset = msg.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")[:max_length]
            except Exception:
                return ""

    @staticmethod
    def _decode_header(value: str) -> str:
        """Decode an email header value that may be MIME-encoded."""
        if not value:
            return ""
        try:
            decoded_parts = email.header.decode_header(value)
            parts = []
            for text, charset in decoded_parts:
                if isinstance(text, bytes):
                    parts.append(text.decode(charset or "utf-8", errors="replace"))
                else:
                    parts.append(text)
            return " ".join(parts)
        except Exception:
            return str(value)
