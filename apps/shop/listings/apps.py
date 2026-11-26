from django.apps import AppConfig


class ListingsConfig(AppConfig):
    """Listings: a piece offered for sale at an asking price."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.shop.listings"
    label = "listings"
    verbose_name = "Shop"

    def ready(self) -> None:
        from apps.shop.listings.permissions import ROLE_PERMISSIONS
        from apps.users.accounts.permissions import connect_role_permissions

        connect_role_permissions(self, ROLE_PERMISSIONS)
