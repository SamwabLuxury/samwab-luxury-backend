"""A provider that keeps payments in memory. For tests only; never on a server.

Tests act as Stripe with ``set_status`` and ``fail_next``. One shared instance is
used (``fake_provider()``), and a test fixture empties it before every test.
"""

import json
from dataclasses import replace
from typing import Any

from apps.money.payments.exceptions import PaymentProviderError, TaxAddressError
from apps.money.payments.providers.base import (
    ProviderEvent,
    ProviderPayment,
    ProviderRefund,
    TaxAddress,
    TaxQuote,
)
from apps.platform.core.ids import new_uuid
from apps.platform.core.money import Money


class FakeProvider:
    name = "fake"

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.payments: dict[str, ProviderPayment] = {}
        self.refunds: dict[str, ProviderRefund] = {}
        self._by_key: dict[str, str] = {}
        self.fail_next = False
        # Sales tax (E22): rates in basis points by "US-IL" (country and state) or
        # "NG" (country); anywhere else 0, as Stripe Tax answers where there is no
        # registration. Tests set ``tax_location_invalid_next`` to act as an address
        # Stripe cannot place.
        self.tax_bps: dict[str, int] = {}
        self.tax_location_invalid_next = False
        self.calculations: dict[str, dict[str, Any]] = {}
        self._linked: dict[str, str] = {}

    def _maybe_fail(self) -> None:
        if self.fail_next:
            self.fail_next = False
            raise PaymentProviderError()

    def create_payment(
        self,
        amount: Money,
        *,
        reference: str,
        idempotency_key: str,
        tax_calculation: str = "",
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
        self._linked[payment_id] = tax_calculation
        return payment

    def linked_calculation(self, payment_id: str) -> str:
        """The tax calculation a payment was created with ("" for none)."""
        return self._linked.get(payment_id, "")

    def calculate_tax(
        self,
        amount: Money,
        *,
        address: TaxAddress,
        reference: str,
        tax_code: str,
        idempotency_key: str,
    ) -> TaxQuote:
        self._maybe_fail()
        if self.tax_location_invalid_next:
            self.tax_location_invalid_next = False
            raise TaxAddressError()
        bps = self.tax_bps.get(f"{address.country}-{address.state}")
        if bps is None:
            bps = self.tax_bps.get(address.country, 0)
        tax = (amount.amount_minor * bps + 5_000) // 10_000  # half up to the cent
        calculation_id = f"taxcalc_fake_{new_uuid().hex}"
        self.calculations[calculation_id] = {
            "amount": amount,
            "address": address,
            "reference": reference,
            "tax_code": tax_code,
            "idempotency_key": idempotency_key,
        }
        return TaxQuote(
            calculation_id=calculation_id,
            tax=Money(tax, amount.currency),
            total=Money(amount.amount_minor + tax, amount.currency),
        )

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
