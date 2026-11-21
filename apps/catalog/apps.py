from django.apps import AppConfig


class CatalogConfig(AppConfig):
    """What can be sold: brands, categories, named designs and materials."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.catalog"
    label = "catalog"
