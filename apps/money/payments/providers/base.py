"""The payment provider interface (the team's "plug-in", architecture rule 7).

Orders and checkout talk to a ``PaymentProvider``, never to Stripe directly, so a
second provider (Paystack, for example) is one new class here and a setting.
Amounts go in and out as ``Money`` (whole cents).
"""

from dataclasses import dataclass, field
from typing import Any, Protocol

from apps.platform.core.money import Money


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
class TaxAddress:
    """Where the piece goes, as the tax service needs it (build E22). Empty parts
    are left out; outside the US only the country matters."""

    line1: str
    line2: str
    city: str
    state: str
    postal_code: str
    country: str


@dataclass(frozen=True)
class TaxQuote:
    """Tax worked out for one order: added on top of the price."""

    calculation_id: str
    tax: Money
    total: Money


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
        self,
        amount: Money,
        *,
        reference: str,
        idempotency_key: str,
        tax_calculation: str = "",
    ) -> ProviderPayment:
        """Start a payment the buyer confirms in the browser.

        The same idempotency key always gives the same payment. ``tax_calculation``
        links a ``calculate_tax`` result, so the provider records the tax when the
        payment succeeds and reverses it on refunds."""
        ...

    def calculate_tax(
        self,
        amount: Money,
        *,
        address: TaxAddress,
        reference: str,
        tax_code: str,
        idempotency_key: str,
    ) -> TaxQuote:
        """Work out the sales tax on one item delivered to ``address`` (tax on top).

        Raises ``TaxAddressError`` when the address cannot be placed."""
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
