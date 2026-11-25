"""Sending email through Resend's HTTPS API (build E14).

Why not SMTP: Render's free plan blocks outgoing SMTP ports (25, 465, 587) since
September 2025, so emails go out as HTTPS requests instead. Docs read for this
build: Resend "Send email" (POST https://api.resend.com/emails, Bearer API key,
JSON: from, to, cc, bcc, reply_to, subject, text, html; answer {"id"}) and "Errors"
(429 and 500/503 may be retried after a delay; 400, 401, 403 and 422 must be fixed
first; until a domain is verified, Resend only sends to your own address).

Uses the standard library only (no new package). Attachments are refused until a
build needs them (the PDF receipt).
"""

import json
import time
import urllib.error
import urllib.request
from collections.abc import Sequence
from typing import Any

from django.core.mail import EmailMessage
from django.core.mail.backends.base import BaseEmailBackend

API_URL = "https://api.resend.com/emails"
USER_AGENT = "samwab-backend/1.0"
RETRY_STATUSES = frozenset({429, 500, 503})
RETRY_AFTER_SECONDS = 1.0


class ResendError(Exception):
    """Resend refused or could not be reached. The message says why, in Resend's words."""


class ResendEmailBackend(BaseEmailBackend):
    """A Django email backend: set it in MAILERS with OPTIONS {"api_key": ...}."""

    def __init__(self, *, api_key: str = "", timeout: float = 10, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        if not api_key:
            raise ResendError("RESEND_API_KEY is empty: put the key in .env or in Render.")
        self.api_key = api_key
        self.timeout = timeout

    def send_messages(self, email_messages: Sequence[EmailMessage]) -> int:
        sent = 0
        for message in email_messages:
            if not message.recipients():
                continue
            self._post(self._payload(message))
            sent += 1
        return sent

    def _payload(self, message: EmailMessage) -> dict[str, Any]:
        if message.attachments:
            raise ResendError("Email attachments are not supported yet.")
        payload: dict[str, Any] = {
            "from": message.from_email,
            "to": list(message.to),
            "subject": message.subject,
        }
        for key, values in (
            ("cc", message.cc),
            ("bcc", message.bcc),
            ("reply_to", message.reply_to),
        ):
            if values:
                payload[key] = list(values)
        if message.content_subtype == "html":
            payload["html"] = message.body
        else:
            payload["text"] = message.body
        for alternative in getattr(message, "alternatives", []):
            if alternative.mimetype == "text/html":
                payload["html"] = alternative.content
        return payload

    def _post(self, payload: dict[str, Any]) -> None:
        request = urllib.request.Request(
            API_URL,
            data=json.dumps(payload).encode(),
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
            },
        )
        for attempt in (1, 2):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout):  # noqa: S310
                    return
            except urllib.error.HTTPError as error:
                if error.code in RETRY_STATUSES and attempt == 1:
                    time.sleep(RETRY_AFTER_SECONDS)
                    continue
                raise ResendError(_reason(error)) from error
            except urllib.error.URLError as error:
                if attempt == 1:
                    time.sleep(RETRY_AFTER_SECONDS)
                    continue
                raise ResendError(f"could not reach Resend ({error.reason}).") from error


def _reason(error: urllib.error.HTTPError) -> str:
    try:
        body = json.loads(error.read())
        return f"{error.code} {body.get('name', 'error')}: {body.get('message', '')}".strip()
    except ValueError:
        return f"{error.code} {error.reason}"
