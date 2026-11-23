from django.apps import AppConfig


class ListingsConfig(AppConfig):
    """Listings: a piece offered for sale at an asking price."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.listings"
    label = "listings"

    def ready(self) -> None:
        from apps.accounts.permissions import connect_role_permissions
        from apps.listings.permissions import ROLE_PERMISSIONS

        connect_role_permissions(self, ROLE_PERMISSIONS)
