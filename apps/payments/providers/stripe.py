"""Stripe, through the official ``stripe`` package (version 17, API ``2026-11-18``).

Payments are PaymentIntents with automatic payment methods: the web app confirms
them with Stripe Elements using ``client_secret``. Every create call sends our
idempotency key, so a retry never charges twice.
"""

import json
import logging
from typing import Any

import stripe

from apps.core.money import Money
from apps.payments.exceptions import PaymentProviderError, WebhookSignatureError
from apps.payments.providers.base import ProviderEvent, ProviderPayment

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
        return ProviderPayment(
            id=intent.id,
            status=intent.status,
            amount=Money(intent.amount, intent.currency.upper()),
            client_secret=intent.client_secret or "",
        )

    def create_payment(
        self, amount: Money, *, reference: str, idempotency_key: str
    ) -> ProviderPayment:
        params: Any = {
            "amount": amount.amount_minor,
            "currency": amount.currency.lower(),
            "automatic_payment_methods": {"enabled": True},
            "metadata": {"reference": reference},
        }
        return self._call(
            "create",
            lambda: self._client.v1.payment_intents.create(
                params, options={"idempotency_key": idempotency_key}
            ),
        )

    def get_payment(self, payment_id: str) -> ProviderPayment:
        return self._call("retrieve", lambda: self._client.v1.payment_intents.retrieve(payment_id))

    def cancel_payment(self, payment_id: str) -> ProviderPayment:
        return self._call("cancel", lambda: self._client.v1.payment_intents.cancel(payment_id))

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
