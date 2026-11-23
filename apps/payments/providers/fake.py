"""A provider that keeps payments in memory. For tests only; never on a server."""

import json
from dataclasses import replace

from apps.core.ids import new_uuid
from apps.core.money import Money
from apps.payments.providers.base import ProviderEvent, ProviderPayment


class FakeProvider:
    name = "fake"

    def __init__(self) -> None:
        self.payments: dict[str, ProviderPayment] = {}
        self._by_key: dict[str, str] = {}

    def create_payment(
        self, amount: Money, *, reference: str, idempotency_key: str
    ) -> ProviderPayment:
        if idempotency_key in self._by_key:
            return self.payments[self._by_key[idempotency_key]]
        payment_id = f"pi_fake_{new_uuid().hex}"
        payment = ProviderPayment(
            id=payment_id,
            status="requires_payment_method",
            amount=amount,
            client_secret=f"{payment_id}_secret_fake",
        )
        self.payments[payment_id] = payment
        self._by_key[idempotency_key] = payment_id
        return payment

    def get_payment(self, payment_id: str) -> ProviderPayment:
        return self.payments[payment_id]

    def cancel_payment(self, payment_id: str) -> ProviderPayment:
        self.payments[payment_id] = replace(self.payments[payment_id], status="canceled")
        return self.payments[payment_id]

    def read_webhook(self, body: bytes, signature: str | None) -> ProviderEvent:
        data = json.loads(body)
        return ProviderEvent(
            id=data["id"], type=data["type"], livemode=bool(data["livemode"]), payload=data
        )
