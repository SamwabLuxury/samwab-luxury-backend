from django.apps import AppConfig


class AuditConfig(AppConfig):
    """The audit log: one append-only row for every change staff make."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.audit"
    label = "audit"
