from django.apps import AppConfig


class OrdersConfig(AppConfig):
    """Orders: a buyer buying one piece from one listing."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.orders"
    label = "orders"

    def ready(self) -> None:
        from apps.orders import services
        from apps.payments import services as payments

        payments.listen(services.on_payment_update)
