from django.apps import AppConfig


class CatalogConfig(AppConfig):
    """What can be sold: brands, categories, named designs and materials."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.catalog"
    label = "catalog"

    def ready(self) -> None:
        from apps.accounts.permissions import connect_role_permissions
        from apps.catalog.permissions import ROLE_PERMISSIONS

        connect_role_permissions(self, ROLE_PERMISSIONS)
