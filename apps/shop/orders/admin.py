"""Orders, payments and refunds, read only, for superusers. Orders change only
through the buyer and the payment provider."""

from typing import Any

from django.contrib import admin
from django.http import HttpRequest

from apps.money.payments.models import Payment
from apps.shop.orders.models import Order


class ReadOnly:
    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


class PaymentInline(ReadOnly, admin.TabularInline):  # type: ignore[type-arg]
    model = Payment
    fields = ("provider_payment_id", "kind", "amount_minor", "status", "failure_reason")
    readonly_fields = fields
    extra = 0


@admin.register(Order)
class OrderAdmin(ReadOnly, admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("order_number", "status", "buyer", "total_minor", "created_at")
    list_filter = ("status",)
    search_fields = ("order_number", "buyer__email")
    exclude = ("shipping_address",)  # personal data; read it through the buyer if needed
    inlines = (PaymentInline,)
