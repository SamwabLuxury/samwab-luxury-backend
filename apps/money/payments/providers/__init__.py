"""Choose the payment provider from settings (``PAYMENT_PROVIDER``)."""

from django.conf import settings

from apps.money.payments.providers.base import PaymentProvider
from apps.money.payments.providers.fake import FakeProvider
from apps.money.payments.providers.stripe import StripeProvider

PROVIDERS = ("stripe", "fake")

_FAKE = FakeProvider()


def fake_provider() -> FakeProvider:
    """The one in-memory provider that tests share (emptied before every test)."""
    return _FAKE


def get_provider() -> PaymentProvider:
    if settings.PAYMENT_PROVIDER == "fake":
        return _FAKE
    return StripeProvider(
        secret_key=settings.STRIPE_SECRET_KEY, webhook_secret=settings.STRIPE_WEBHOOK_SECRET
    )
