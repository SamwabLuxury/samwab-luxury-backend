from django.apps import AppConfig


class IdempotencyConfig(AppConfig):
    """Idempotency keys: a request sent twice does its work once."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.idempotency"
    label = "idempotency"
