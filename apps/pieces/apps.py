from django.apps import AppConfig


class PiecesConfig(AppConfig):
    """Physical pieces: one row per object Samwab holds, sells or has checked."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.pieces"
    label = "pieces"

    def ready(self) -> None:
        from apps.accounts.permissions import connect_role_permissions
        from apps.pieces.permissions import ROLE_PERMISSIONS

        connect_role_permissions(self, ROLE_PERMISSIONS)
