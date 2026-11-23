"""A provider that keeps payments in memory. For tests only; never on a server.

Tests act as Stripe with ``set_status`` and ``fail_next``. One shared instance is
used (``fake_provider()``), and a test fixture empties it before every test.
"""

import json
from dataclasses import replace

from apps.core.ids import new_uuid
from apps.core.money import Money
from apps.payments.exceptions import PaymentProviderError
from apps.payments.providers.base import ProviderEvent, ProviderPayment, ProviderRefund


class FakeProvider:
    name = "fake"

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.payments: dict[str, ProviderPayment] = {}
        self.refunds: dict[str, ProviderRefund] = {}
        self._by_key: dict[str, str] = {}
        self.fail_next = False

    def _maybe_fail(self) -> None:
        if self.fail_next:
            self.fail_next = False
            raise PaymentProviderError()

    def create_payment(
        self, amount: Money, *, reference: str, idempotency_key: str
    ) -> ProviderPayment:
        self._maybe_fail()
        if idempotency_key in self._by_key:
            return self.payments[self._by_key[idempotency_key]]
        payment_id = f"pi_fake_{new_uuid().hex}"
        payment = ProviderPayment(
            id=payment_id,
            status="requires_payment_method",
            amount=amount,
            client_secret=f"{payment_id}_secret_fake",
            amount_received=Money(0, amount.currency),
        )
        self.payments[payment_id] = payment
        self._by_key[idempotency_key] = payment_id
        return payment

    def set_status(
        self,
        payment_id: str,
        status: str,
        *,
        amount_received: int | None = None,
        failure_reason: str = "",
    ) -> None:
        """Act as Stripe: the payment is now in ``status``."""
        payment = self.payments[payment_id]
        if amount_received is None:
            amount_received = payment.amount.amount_minor if status == "succeeded" else 0
        self.payments[payment_id] = replace(
            payment,
            status=status,
            amount_received=Money(amount_received, payment.amount.currency),
            failure_reason=failure_reason,
        )

    def get_payment(self, payment_id: str) -> ProviderPayment:
        self._maybe_fail()
        return self.payments[payment_id]

    def cancel_payment(self, payment_id: str) -> ProviderPayment:
        self._maybe_fail()
        if self.payments[payment_id].status == "succeeded":
            raise PaymentProviderError()  # as Stripe: a succeeded payment cannot be cancelled
        self.set_status(payment_id, "canceled")
        return self.payments[payment_id]

    def refund_payment(
        self, payment_id: str, amount: Money, *, idempotency_key: str
    ) -> ProviderRefund:
        self._maybe_fail()
        refund = ProviderRefund(id=f"re_fake_{idempotency_key}", status="succeeded", amount=amount)
        self.refunds[refund.id] = refund
        return refund

    def read_webhook(self, body: bytes, signature: str | None) -> ProviderEvent:
        data = json.loads(body)
        return ProviderEvent(
            id=data["id"], type=data["type"], livemode=bool(data["livemode"]), payload=data
        )
