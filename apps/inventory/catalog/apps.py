from django.apps import AppConfig


class CatalogConfig(AppConfig):
    """What can be sold: brands, categories, named designs and materials."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.inventory.catalog"
    label = "catalog"
    verbose_name = "Catalog and prices"

    def ready(self) -> None:
        from apps.inventory.catalog.permissions import ROLE_PERMISSIONS
        from apps.users.accounts.permissions import connect_role_permissions

        connect_role_permissions(self, ROLE_PERMISSIONS)
