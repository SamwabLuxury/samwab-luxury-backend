"""Prove the payment keys work: make a $1.00 test payment, then cancel it.

Refuses live keys, so it can never charge anyone.
"""

from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.core.ids import new_uuid
from apps.core.money import Money
from apps.payments.exceptions import PaymentProviderError
from apps.payments.providers import get_provider


def is_live_key(key: str) -> bool:
    """Live secret and restricted keys start sk_live_ and rk_live_ (Stripe's API keys docs)."""
    return key.startswith(("sk_live_", "rk_live_"))


class Command(BaseCommand):
    help = "Make a $1.00 test payment with the payment provider, then cancel it."

    def handle(self, *args: Any, **options: Any) -> None:
        if settings.PAYMENT_PROVIDER == "stripe":
            key = settings.STRIPE_SECRET_KEY
            if not key:
                raise CommandError(
                    "Set STRIPE_SECRET_KEY (the sandbox's sk_test_ key) in .env first."
                )
            if is_live_key(key):
                raise CommandError(
                    "This is a live key. check_payments only runs with sandbox keys."
                )
        provider = get_provider()
        try:
            payment = provider.create_payment(
                Money(100), reference="check_payments", idempotency_key=str(new_uuid())
            )
            self.stdout.write(
                f"Created a {payment.amount} test payment: {payment.id} ({payment.status})."
            )
            cancelled = provider.cancel_payment(payment.id)
        except PaymentProviderError as failure:
            raise CommandError(
                f"{failure.message} Check STRIPE_SECRET_KEY, and that you are online."
            ) from failure
        self.stdout.write(f"Then cancelled it ({cancelled.status}).")
        self.stdout.write(self.style.SUCCESS(f"Payments are working with {provider.name}."))
