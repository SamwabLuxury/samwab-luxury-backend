from django.apps import AppConfig


class AddressesConfig(AppConfig):
    """Delivery addresses that buyers keep on their account, stored encrypted."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.addresses"
    label = "addresses"
