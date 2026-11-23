from django.apps import AppConfig


class CoreConfig(AppConfig):
    """Shared building blocks used by every other app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    label = "core"

    def ready(self) -> None:
        from apps.core import checks  # noqa: F401  (registers the system checks)
