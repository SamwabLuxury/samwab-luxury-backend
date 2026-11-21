from django.apps import AppConfig


class PiecesConfig(AppConfig):
    """Physical pieces: one row per object Samwab holds, sells or has checked."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.pieces"
    label = "pieces"
