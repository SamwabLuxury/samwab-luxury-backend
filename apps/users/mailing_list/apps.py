from django.apps import AppConfig


class MailingListConfig(AppConfig):
    """The mailing list: "Join the list", confirmed by email, early access to drops."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.users.mailing_list"
    label = "mailing_list"
    verbose_name = "mailing list"

    def ready(self) -> None:
        from apps.users.accounts.permissions import connect_role_permissions
        from apps.users.mailing_list.permissions import ROLE_PERMISSIONS

        connect_role_permissions(self, ROLE_PERMISSIONS)
