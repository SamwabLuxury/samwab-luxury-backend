from django.apps import AppConfig


class MailingListConfig(AppConfig):
    """The mailing list: "Join the list", confirmed by email, early access to drops."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.users.mailing_list"
    label = "mailing_list"
    verbose_name = "mailing list"
