"""The payment provider interface (the team's "plug-in", architecture rule 7).

Orders and checkout talk to a ``PaymentProvider``, never to Stripe directly, so a
second provider (Paystack, for example) is one new class here and a setting.
Amounts go in and out as ``Money`` (whole cents).
"""

from dataclasses import dataclass, field
from typing import Any, Protocol

from apps.core.money import Money


@dataclass(frozen=True)
class ProviderPayment:
    """A payment as the provider sees it."""

    id: str
    status: str
    amount: Money
    client_secret: str = field(repr=False)  # the browser needs it; never log it
    amount_received: Money | None = None
    failure_reason: str = ""  # the last attempt's error, for support ("card_declined: ...")


@dataclass(frozen=True)
class ProviderRefund:
    id: str
    status: str
    amount: Money


@dataclass(frozen=True)
class ProviderEvent:
    """A webhook event that passed the provider's signature check."""

    id: str
    type: str
    livemode: bool
    payload: dict[str, Any]


class PaymentProvider(Protocol):
    name: str

    def create_payment(
        self, amount: Money, *, reference: str, idempotency_key: str
    ) -> ProviderPayment:
        """Start a payment the buyer confirms in the browser.

        The same idempotency key always gives the same payment."""
        ...

    def get_payment(self, payment_id: str) -> ProviderPayment: ...

    def cancel_payment(self, payment_id: str) -> ProviderPayment: ...

    def refund_payment(
        self, payment_id: str, amount: Money, *, idempotency_key: str
    ) -> ProviderRefund: ...

    def read_webhook(self, body: bytes, signature: str | None) -> ProviderEvent:
        """Check the signature on the raw body and return the event, or raise
        ``WebhookSignatureError``."""
        ...
