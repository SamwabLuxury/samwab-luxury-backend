"""Writes for payments: starting, cancelling and refunding payments, and acting on
what the provider tells us.

Orders call these functions; this module never imports orders. When a payment
changes, the apps that care are told through ``listen`` (orders registers in its
``ready()``), so the payment provider stays a plug-in.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.core.money import Money
from apps.payments.models import Payment, Refund, StripeEvent
from apps.payments.providers import get_provider
from apps.payments.providers.base import ProviderEvent, ProviderPayment

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PaymentUpdate:
    """A payment of ours and what the provider says about it now."""

    payment: Payment
    seen: ProviderPayment


Listener = Callable[[PaymentUpdate], None]
_listeners: list[Listener] = []


def listen(listener: Listener) -> None:
    """Call ``listener`` whenever one of our payments changes."""
    if listener not in _listeners:
        _listeners.append(listener)


def start_payment(*, order: Any, amount: Money, reference: str, key: str) -> tuple[Payment, str]:
    """Ask the provider for a payment the buyer confirms in the browser.

    ``key`` makes it safe to repeat: the same key never makes a second payment.
    Returns the payment and the client secret for the browser.
    """
    seen = get_provider().create_payment(amount, reference=reference, idempotency_key=key)
    payment = Payment.objects.create(
        order=order,
        provider_payment_id=seen.id,
        amount_minor=amount.amount_minor,
        currency=amount.currency,
        status=seen.status,
        idempotency_key=key,
    )
    return payment, seen.client_secret


@transaction.atomic
def payment_changed(provider_payment_id: str, *, source: str) -> Payment | None:
    """Read the payment's current state from the provider and tell the listeners.

    The provider's answer, not the event that woke us, decides: so a repeated,
    late or out-of-order event can never move a payment backwards. Payments that
    are not ours (made in the dashboard, or by ``check_payments``) are ignored.
    """
    payment = (
        Payment.objects.select_for_update(of=("self",))
        .filter(provider_payment_id=provider_payment_id)
        .first()
    )
    if payment is None:
        return None
    seen = get_provider().get_payment(provider_payment_id)
    payment.status = seen.status
    payment.failure_reason = seen.failure_reason[:255]
    payment.save(update_fields=["status", "failure_reason", "updated_at"])
    logger.info("payment %s is %s (%s)", payment.provider_payment_id, seen.status, source)
    for listener in _listeners:
        listener(PaymentUpdate(payment, seen))
    return payment


def cancel_payment(payment: Payment) -> ProviderPayment:
    """Cancel at the provider. Raises ``PaymentProviderError`` if it cannot (already paid)."""
    seen = get_provider().cancel_payment(payment.provider_payment_id)
    payment.status = seen.status
    payment.save(update_fields=["status", "updated_at"])
    return seen


def refund(payment: Payment, *, reason: str, by: User | None = None) -> Refund:
    """Give the whole payment back. Safe to repeat: the key is per payment and reason."""
    amount = Money(payment.amount_minor, payment.currency)
    done = get_provider().refund_payment(
        payment.provider_payment_id, amount, idempotency_key=f"refund-{payment.pk}-{reason}"
    )
    found, _ = Refund.objects.get_or_create(
        provider_refund_id=done.id,
        defaults={
            "payment": payment,
            "amount_minor": done.amount.amount_minor,
            "currency": done.amount.currency,
            "reason": reason,
            "status": done.status,
            "created_by": by,
        },
    )
    logger.warning("refunded %s for %s (%s)", amount, payment.provider_payment_id, reason)
    return found


def _without_secrets(data: Any) -> Any:
    """Drop every ``client_secret``: it lets anyone finish that payment, and we never need it."""
    if isinstance(data, dict):
        return {k: _without_secrets(v) for k, v in data.items() if k != "client_secret"}
    if isinstance(data, list):
        return [_without_secrets(item) for item in data]
    return data


def record_stripe_event(event: ProviderEvent) -> tuple[StripeEvent, bool]:
    """Store a verified event once. Returns the row and whether it was new.

    Stripe may deliver an event more than once; the event id is the primary key,
    so a repeat changes nothing (Stripe's webhook docs: track event ids).
    """
    return StripeEvent.objects.get_or_create(
        id=event.id,
        defaults={
            "type": event.type,
            "livemode": event.livemode,
            "payload": _without_secrets(event.payload),
        },
    )


def handle_stripe_event(stored: StripeEvent) -> None:
    """Act on a stored event once. If it fails, keep the error and raise, so the
    webhook answers 500 and Stripe sends the event again."""
    if stored.processed_at is not None:
        return
    stored.attempts += 1
    try:
        with transaction.atomic():
            if stored.type.startswith("payment_intent."):
                payment_changed(
                    stored.payload["data"]["object"]["id"], source=f"webhook {stored.id}"
                )
            stored.processed_at = timezone.now()
            stored.last_error = ""
            stored.save(update_fields=["attempts", "processed_at", "last_error"])
    except Exception as failure:
        stored.last_error = f"{type(failure).__name__}: {failure}"[:2000]
        stored.save(update_fields=["attempts", "last_error"])
        raise
