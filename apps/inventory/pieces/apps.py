from django.apps import AppConfig


class PiecesConfig(AppConfig):
    """Physical pieces: one row per object Samwab holds, sells or has checked."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.inventory.pieces"
    label = "pieces"
    verbose_name = "Stock"

    def ready(self) -> None:
        from apps.inventory.pieces.permissions import ROLE_PERMISSIONS
        from apps.users.accounts.permissions import connect_role_permissions

        connect_role_permissions(self, ROLE_PERMISSIONS)
