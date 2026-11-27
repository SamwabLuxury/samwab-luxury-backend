from django.apps import AppConfig


class PassportsConfig(AppConfig):
    """Passports: the public record of a verified piece, its condition and restorations."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.inventory.passports"
    label = "passports"
    verbose_name = "Passports"

    def ready(self) -> None:
        from apps.inventory.passports.permissions import ROLE_PERMISSIONS
        from apps.users.accounts.permissions import connect_role_permissions

        connect_role_permissions(self, ROLE_PERMISSIONS)
