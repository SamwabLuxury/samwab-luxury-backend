"""Orders, payments and refunds, read only, for superusers. Orders change only
through the buyer and the payment provider."""

from typing import Any

from django.contrib import admin
from django.http import HttpRequest

from apps.money.payments.models import Payment
from apps.platform.core.admin_dollars import dollars_column
from apps.platform.core.admin_look import ModelAdmin, TabularInline
from apps.shop.orders.models import Order

MONEY_LABELS = (
    ("item", "item_minor"),
    ("commission", "commission_minor"),
    ("seller_share", "seller_share_minor"),
    ("tax", "tax_minor"),
    ("total", "total_minor"),
    ("reservation_deposit", "reservation_deposit_minor"),
)
MONEY_COLUMNS = tuple(column for _, column in MONEY_LABELS)


class ReadOnly:
    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


class PaymentInline(ReadOnly, TabularInline):  # type: ignore[type-arg]
    model = Payment
    fields = ("provider_payment_id", "kind", "amount", "status", "failure_reason")
    readonly_fields = fields
    extra = 0
    amount = dollars_column("amount_minor", "Amount")


@admin.register(Order)
class OrderAdmin(ReadOnly, ModelAdmin):  # type: ignore[type-arg]
    list_display = ("order_number", "status", "buyer", "total", "created_at")
    list_filter = ("status",)
    search_fields = ("order_number", "buyer__email")
    # shipping_address is personal data: read it through the buyer if needed. The cents
    # columns are shown in dollars below instead (E16).
    exclude = ("shipping_address", *MONEY_COLUMNS)
    # Fields the code alone sets (editable=False) are shown only when listed here: the
    # Stripe Tax calculation behind the tax (E22) and when the confirmation went (E21).
    readonly_fields = (
        *(name for name, _ in MONEY_LABELS),
        "tax_calculation_id",
        "confirmation_sent_at",
    )
    item = dollars_column("item_minor", "Piece price")
    commission = dollars_column("commission_minor", "Our commission")
    seller_share = dollars_column("seller_share_minor", "Seller's share")
    tax = dollars_column("tax_minor", "Sales tax")
    total = dollars_column("total_minor", "Total paid")
    reservation_deposit = dollars_column("reservation_deposit_minor", "Reservation deposit")
    inlines = (PaymentInline,)
