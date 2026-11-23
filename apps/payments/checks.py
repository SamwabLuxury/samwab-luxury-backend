"""System checks for payment settings."""

from typing import Any

from django.conf import settings
from django.core.checks import Error, Warning, register

from apps.payments.providers import PROVIDERS


@register()
def check_payment_settings(app_configs: Any, **kwargs: Any) -> list[Error | Warning]:
    problems: list[Error | Warning] = []
    if settings.PAYMENT_PROVIDER not in PROVIDERS:
        problems.append(
            Error(
                f"PAYMENT_PROVIDER must be one of {', '.join(PROVIDERS)}.",
                id="payments.E001",
            )
        )
    elif settings.PAYMENT_PROVIDER == "stripe":
        for name in ("STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET"):
            if not getattr(settings, name):
                problems.append(
                    Warning(
                        f"{name} is not set, so payments will not work.",
                        hint="Copy it from the Stripe sandbox into .env (README, Payments).",
                        id="payments.W001",
                    )
                )
    return problems
