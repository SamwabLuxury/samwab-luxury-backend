from django.apps import AppConfig


class LegalConfig(AppConfig):
    """Legal texts (terms, privacy, returns...), who accepted which version, and consents."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.users.legal"
    label = "legal"
    verbose_name = "legal texts"
