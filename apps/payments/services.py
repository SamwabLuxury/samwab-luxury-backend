"""Writes for payments."""

from apps.payments.models import StripeEvent
from apps.payments.providers.base import ProviderEvent


def record_stripe_event(event: ProviderEvent) -> tuple[StripeEvent, bool]:
    """Store a verified event once. Returns the row and whether it was new.

    Stripe may deliver an event more than once; the event id is the primary key,
    so a repeat changes nothing (Stripe's webhook docs: track event ids).
    """
    return StripeEvent.objects.get_or_create(
        id=event.id,
        defaults={"type": event.type, "livemode": event.livemode, "payload": event.payload},
    )
