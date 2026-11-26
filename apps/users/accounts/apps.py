from django.apps import AppConfig


class AccountsConfig(AppConfig):
    """People who use Samwab: buyers, owners, dealers and staff."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.users.accounts"
    label = "accounts"
    verbose_name = "People"
