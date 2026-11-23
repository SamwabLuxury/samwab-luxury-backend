from django.apps import AppConfig


class PaymentsConfig(AppConfig):
    """Payments: the only app that talks to a payment provider (architecture rule 7)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.money.payments"
    label = "payments"

    def ready(self) -> None:
        from apps.money.payments import checks  # noqa: F401  (registers the system checks)
