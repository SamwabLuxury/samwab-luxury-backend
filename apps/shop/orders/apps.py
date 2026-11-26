from django.apps import AppConfig


class OrdersConfig(AppConfig):
    """Orders: a buyer buying one piece from one listing."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.shop.orders"
    label = "orders"

    def ready(self) -> None:
        from apps.money.payments import services as payments
        from apps.shop.orders import services

        payments.listen(services.on_payment_update)

        from apps.shop.orders.permissions import ROLE_PERMISSIONS
        from apps.users.accounts.permissions import connect_role_permissions

        connect_role_permissions(self, ROLE_PERMISSIONS)
