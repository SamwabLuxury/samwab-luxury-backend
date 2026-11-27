"""Stripe, through the official ``stripe`` package (version 17, API ``2026-11-18``).

Payments are PaymentIntents with automatic payment methods: the web app confirms
them with Stripe Elements using ``client_secret``. Every create call sends our
idempotency key, so a retry never charges twice.
"""

import json
import logging
from typing import Any

import stripe

from apps.money.payments.exceptions import (
    PaymentProviderError,
    TaxAddressError,
    WebhookSignatureError,
)
from apps.money.payments.providers.base import (
    ProviderEvent,
    ProviderPayment,
    ProviderRefund,
    TaxAddress,
    TaxQuote,
)
from apps.platform.core.money import Money

logger = logging.getLogger(__name__)


class StripeProvider:
    name = "stripe"

    def __init__(
        self, *, secret_key: str, webhook_secret: str, http_client: stripe.HTTPClient | None = None
    ) -> None:
        self._client = stripe.StripeClient(
            secret_key, max_network_retries=2, http_client=http_client
        )
        self._webhook_secret = webhook_secret

    def _call(self, what: str, request: Any) -> ProviderPayment:
        try:
            intent = request()
        except stripe.StripeError as failure:
            # Logged with Stripe's request id for support; the message never reaches users.
            logger.warning(
                "stripe %s failed: %s (request %s)", what, failure.code, failure.request_id
            )
            raise PaymentProviderError() from failure
        currency = intent.currency.upper()
        data = intent.to_dict()  # Stripe objects are not dicts; optional fields may be absent
        error = data.get("last_payment_error") or {}
        reason = ": ".join(part for part in (error.get("code"), error.get("message")) if part)
        received = data.get("amount_received")
        return ProviderPayment(
            id=intent.id,
            status=intent.status,
            amount=Money(intent.amount, currency),
            client_secret=intent.client_secret or "",
            amount_received=None if received is None else Money(received, currency),
            failure_reason=reason,
        )

    def create_payment(
        self,
        amount: Money,
        *,
        reference: str,
        idempotency_key: str,
        tax_calculation: str = "",
    ) -> ProviderPayment:
        params: Any = {
            "amount": amount.amount_minor,
            "currency": amount.currency.lower(),
            "automatic_payment_methods": {"enabled": True},
            "metadata": {"reference": reference},
        }
        if tax_calculation:
            # Stripe's "basic" Stripe Tax with PaymentIntents: the linked calculation
            # becomes a tax transaction when the payment succeeds, and refunds reverse
            # it. Storing the id in metadata alone would not (docs.stripe.com/tax/
            # payment-intent/simplified).
            params["hooks"] = {"inputs": {"tax": {"calculation": tax_calculation}}}
        return self._call(
            "create",
            lambda: self._client.v1.payment_intents.create(
                params, options={"idempotency_key": idempotency_key}
            ),
        )

    def calculate_tax(
        self,
        amount: Money,
        *,
        address: TaxAddress,
        reference: str,
        tax_code: str,
        idempotency_key: str,
    ) -> TaxQuote:
        where = {
            "line1": address.line1,
            "line2": address.line2,
            "city": address.city,
            "state": address.state,
            "postal_code": address.postal_code,
            "country": address.country,
        }
        params: Any = {
            "currency": amount.currency.lower(),
            "line_items": [
                {
                    "amount": amount.amount_minor,
                    "reference": reference,
                    "tax_code": tax_code,
                    "tax_behavior": "exclusive",  # prices are shown before tax (D69)
                }
            ],
            "customer_details": {
                "address": {name: value for name, value in where.items() if value},
                "address_source": "shipping",
            },
        }
        try:
            calculation = self._client.v1.tax.calculations.create(
                params, options={"idempotency_key": idempotency_key}
            )
        except stripe.StripeError as failure:
            logger.warning(
                "stripe tax calculation failed: %s (request %s)",
                failure.code,
                failure.request_id,
            )
            if failure.code == "customer_tax_location_invalid":
                raise TaxAddressError() from failure
            raise PaymentProviderError() from failure
        currency = calculation.currency.upper()
        return TaxQuote(
            calculation_id=calculation.id or "",
            tax=Money(calculation.tax_amount_exclusive, currency),
            total=Money(calculation.amount_total, currency),
        )

    def get_payment(self, payment_id: str) -> ProviderPayment:
        return self._call("retrieve", lambda: self._client.v1.payment_intents.retrieve(payment_id))

    def cancel_payment(self, payment_id: str) -> ProviderPayment:
        return self._call("cancel", lambda: self._client.v1.payment_intents.cancel(payment_id))

    def refund_payment(
        self, payment_id: str, amount: Money, *, idempotency_key: str
    ) -> ProviderRefund:
        params: Any = {"payment_intent": payment_id, "amount": amount.amount_minor}
        try:
            refund = self._client.v1.refunds.create(
                params, options={"idempotency_key": idempotency_key}
            )
        except stripe.StripeError as failure:
            logger.warning(
                "stripe refund failed: %s (request %s)", failure.code, failure.request_id
            )
            raise PaymentProviderError() from failure
        return ProviderRefund(
            id=refund.id,
            status=refund.status or "",
            amount=Money(refund.amount, refund.currency.upper()),
        )

    def read_webhook(self, body: bytes, signature: str | None) -> ProviderEvent:
        if not self._webhook_secret:
            raise WebhookSignatureError("No webhook secret is set (STRIPE_WEBHOOK_SECRET).")
        try:
            event = self._client.construct_event(body, signature, self._webhook_secret)
        except (stripe.SignatureVerificationError, ValueError) as refused:
            # ValueError covers a body that is signed but is not JSON.
            raise WebhookSignatureError() from refused
        return ProviderEvent(
            id=event.id, type=event.type, livemode=bool(event.livemode), payload=json.loads(body)
        )
