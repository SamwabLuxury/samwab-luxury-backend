"""Stand-ins for Stripe in tests: a recording HTTP client and signed webhook bodies."""

import hashlib
import hmac
import json
import time
from collections.abc import Mapping
from typing import Any
from urllib.parse import parse_qs

from stripe import HTTPClient

WEBHOOK_SECRET = "whsec_test_only"  # noqa: S105 (made up)


def payment_intent(**fields: Any) -> dict[str, Any]:
    return {
        "id": "pi_test_123",
        "object": "payment_intent",
        "amount": 1250000,
        "currency": "usd",
        "status": "requires_payment_method",
        "client_secret": "pi_test_123_secret_abc",
        **fields,
    }


class RecordingHTTPClient(HTTPClient):
    """Answers every Stripe call with a canned body and remembers what was sent."""

    name = "recording"

    def __init__(self, body: dict[str, Any] | None = None, status: int = 200) -> None:
        super().__init__()
        self.body = body if body is not None else payment_intent()
        self.status = status
        self.calls: list[dict[str, Any]] = []

    def request(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str] | None,
        post_data: Any = None,
        *,
        _usage: Any = None,
    ) -> tuple[str, int, Mapping[str, str]]:
        sent = parse_qs(post_data.decode() if isinstance(post_data, bytes) else post_data or "")
        self.calls.append(
            {"method": method, "url": url, "headers": dict(headers or {}), "data": sent}
        )
        return json.dumps(self.body), self.status, {"Request-Id": "req_test"}


def signed(
    event: dict[str, Any], secret: str = WEBHOOK_SECRET, at: int | None = None
) -> tuple[bytes, str]:
    """A webhook body and the Stripe-Signature header Stripe would send with it."""
    body = json.dumps(event).encode()
    timestamp = at if at is not None else int(time.time())
    signature = hmac.new(
        secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256
    ).hexdigest()
    return body, f"t={timestamp},v1={signature}"


def event(**fields: Any) -> dict[str, Any]:
    return {
        "id": "evt_test_1",
        "object": "event",
        "type": "payment_intent.succeeded",
        "livemode": False,
        "created": 1795440000,
        "data": {"object": payment_intent(status="succeeded")},
        **fields,
    }
