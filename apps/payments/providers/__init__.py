"""Choose the payment provider from settings (``PAYMENT_PROVIDER``)."""

from django.conf import settings

from apps.payments.providers.base import PaymentProvider
from apps.payments.providers.fake import FakeProvider
from apps.payments.providers.stripe import StripeProvider

PROVIDERS = ("stripe", "fake")


def get_provider() -> PaymentProvider:
    if settings.PAYMENT_PROVIDER == "fake":
        return FakeProvider()
    return StripeProvider(
        secret_key=settings.STRIPE_SECRET_KEY, webhook_secret=settings.STRIPE_WEBHOOK_SECRET
    )
