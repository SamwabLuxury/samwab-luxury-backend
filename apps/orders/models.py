"""An order: one buyer buying one piece from one listing (architecture rule 10).

This build covers house stock paid in full. Prices are copied from the listing
when the order is made, so a later price change never alters it. The columns
for consignment (fee schedule, commission), reservations, intake, delivery and
returns arrive with the builds that use them; this build adds ``hold_until``
(the 15-minute checkout hold), which the data model does not have yet.
"""

from django.conf import settings
from django.db import models

from apps.core.fields import EncryptedTextField
from apps.core.models import BaseModel
from apps.core.money import DEFAULT_CURRENCY, Money
from apps.listings.enums import AcquisitionSource
from apps.listings.models import Listing
from apps.orders.enums import CancelReason, Channel, DeliveryChoice, OrderKind, OrderStatus
from apps.pieces.models import Piece


class Order(BaseModel):
    order_number = models.CharField(max_length=20, unique=True, editable=False)
    kind = models.CharField(max_length=20, choices=OrderKind.choices)
    listing = models.ForeignKey(Listing, on_delete=models.PROTECT, related_name="orders")
    piece = models.ForeignKey(Piece, on_delete=models.PROTECT, related_name="orders")
    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="purchases"
    )
    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="sales"
    )
    channel = models.CharField(max_length=20, choices=Channel.choices)
    acquisition_source = models.CharField(
        max_length=30, choices=AcquisitionSource.choices, blank=True
    )
    known_before = models.BooleanField(null=True, blank=True)
    status = models.CharField(
        max_length=30, choices=OrderStatus.choices, default=OrderStatus.PENDING_PAYMENT
    )
    commission_bps = models.PositiveIntegerField(default=0)
    item_minor = models.PositiveBigIntegerField()
    commission_minor = models.PositiveBigIntegerField(default=0)
    seller_share_minor = models.PositiveBigIntegerField()
    tax_minor = models.PositiveBigIntegerField(default=0)
    total_minor = models.PositiveBigIntegerField()
    reservation_deposit_minor = models.PositiveBigIntegerField(default=0)
    currency = models.CharField(max_length=3, default=DEFAULT_CURRENCY)
    delivery_choice = models.CharField(max_length=20, choices=DeliveryChoice.choices)
    shipping_address = EncryptedTextField(
        db_column="shipping_address_enc", null=True, blank=True, help_text="A copy, not a link."
    )
    hold_until = models.DateTimeField(help_text="Unpaid by then, the piece goes back on sale.")
    paid_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=40, choices=CancelReason.choices, blank=True)

    class Meta:
        db_table = "orders"
        ordering = ("-id",)
        constraints = (
            models.UniqueConstraint(
                fields=("listing",),
                condition=models.Q(status=OrderStatus.PENDING_PAYMENT),
                name="orders_one_pending_per_listing",
            ),
            models.CheckConstraint(
                condition=models.Q(total_minor=models.F("item_minor") + models.F("tax_minor")),
                name="orders_total_is_item_plus_tax",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    seller_share_minor=models.F("item_minor") - models.F("commission_minor")
                ),
                name="orders_seller_share_is_item_less_commission",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=OrderStatus.values), name="orders_status_is_known"
            ),
        )

    def __str__(self) -> str:
        return f"{self.order_number} · {self.status}"

    def money(self, minor: int) -> Money:
        return Money(minor, self.currency)
