from typing import Any

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.inventory.pieces.api.serializers import PublicPieceSerializer
from apps.platform.core.api.money import MoneySerializer
from apps.shop.listings.enums import AcquisitionSource
from apps.shop.orders.enums import DeliveryChoice, OrderStatus
from apps.shop.orders.models import Order
from apps.users.addresses.models import Address


class OrderCreateSerializer(serializers.Serializer[None]):
    """``POST /api/v1/orders/``. The price is never sent: it comes from the listing."""

    listing_id = serializers.UUIDField()
    payment_option = serializers.ChoiceField(choices=["pay_in_full", "reserve"])
    delivery_choice = serializers.ChoiceField(choices=DeliveryChoice.choices)
    shipping_address_id = serializers.UUIDField(
        required=False, help_text="One of your addresses; needed for courier delivery."
    )
    acquisition_source = serializers.ChoiceField(
        choices=AcquisitionSource.choices, required=False, allow_blank=True
    )
    known_before = serializers.BooleanField(required=False, allow_null=True, default=None)

    def validate(self, data: dict[str, Any]) -> dict[str, Any]:
        address_id = data.pop("shipping_address_id", None)
        if address_id is not None:
            address = Address.objects.filter(pk=address_id, user=self.context["user"]).first()
            if address is None:
                raise serializers.ValidationError(
                    {"shipping_address_id": "Not one of your addresses."}
                )
            data["shipping_address"] = address
        elif data["delivery_choice"] == DeliveryChoice.BUYER_COURIER:
            raise serializers.ValidationError(
                {"shipping_address_id": "Choose one of your addresses for the courier."}
            )
        return data


class TimelineStepSerializer(serializers.Serializer[dict[str, Any]]):
    status = serializers.ChoiceField(choices=OrderStatus.choices)
    at = serializers.DateTimeField()


class OrderSerializer(serializers.ModelSerializer[Order]):
    """The contract's Order. The buyer sees ``tax`` and ``amount_due``; the seller sees
    ``seller_share`` and ``commission`` instead."""

    listing_id = serializers.UUIDField()
    piece = PublicPieceSerializer()
    item = serializers.SerializerMethodField()
    tax = serializers.SerializerMethodField()
    total = serializers.SerializerMethodField()
    reservation_deposit = serializers.SerializerMethodField()
    amount_due = serializers.SerializerMethodField(help_text="What the buyer still has to pay now.")
    seller_share = serializers.SerializerMethodField()
    commission = serializers.SerializerMethodField()
    pay_by = serializers.DateTimeField(
        source="hold_until", help_text="Unpaid by then, the order is cancelled (15 minutes)."
    )
    reserved_until = serializers.SerializerMethodField()
    bring_in_deadline = serializers.SerializerMethodField()
    return_window_ends_at = serializers.SerializerMethodField()
    buyer_confirmation_required = serializers.SerializerMethodField()
    timeline = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = (
            "id",
            "order_number",
            "kind",
            "channel",
            "status",
            "listing_id",
            "piece",
            "item",
            "tax",
            "total",
            "reservation_deposit",
            "amount_due",
            "seller_share",
            "commission",
            "pay_by",
            "reserved_until",
            "delivery_choice",
            "bring_in_deadline",
            "return_window_ends_at",
            "buyer_confirmation_required",
            "cancel_reason",
            "timeline",
            "created_at",
        )

    def _money(self, order: Order, minor: int) -> dict[str, Any]:
        return dict(MoneySerializer(order.money(minor)).data)

    @extend_schema_field(MoneySerializer)
    def get_item(self, order: Order) -> dict[str, Any]:
        return self._money(order, order.item_minor)

    @extend_schema_field(MoneySerializer)
    def get_tax(self, order: Order) -> dict[str, Any]:
        return self._money(order, order.tax_minor)

    @extend_schema_field(MoneySerializer)
    def get_total(self, order: Order) -> dict[str, Any]:
        return self._money(order, order.total_minor)

    @extend_schema_field(MoneySerializer)
    def get_reservation_deposit(self, order: Order) -> dict[str, Any]:
        return self._money(order, order.reservation_deposit_minor)

    @extend_schema_field(MoneySerializer)
    def get_amount_due(self, order: Order) -> dict[str, Any]:
        due = order.total_minor if order.status == OrderStatus.PENDING_PAYMENT else 0
        return self._money(order, due)

    @extend_schema_field(MoneySerializer)
    def get_seller_share(self, order: Order) -> dict[str, Any]:
        return self._money(order, order.seller_share_minor)

    @extend_schema_field(MoneySerializer)
    def get_commission(self, order: Order) -> dict[str, Any]:
        return self._money(order, order.commission_minor)

    @extend_schema_field(serializers.DateTimeField(allow_null=True))
    def get_reserved_until(self, order: Order) -> None:
        return None  # reservations with a deposit come later

    @extend_schema_field(serializers.DateTimeField(allow_null=True))
    def get_bring_in_deadline(self, order: Order) -> None:
        return None  # house stock is already in the vault

    @extend_schema_field(serializers.DateTimeField(allow_null=True))
    def get_return_window_ends_at(self, order: Order) -> None:
        return None  # starts at delivery (later build)

    def get_buyer_confirmation_required(self, order: Order) -> bool:
        return False

    @extend_schema_field(TimelineStepSerializer(many=True))
    def get_timeline(self, order: Order) -> list[dict[str, Any]]:
        steps = [(OrderStatus.PENDING_PAYMENT, order.created_at)]
        if order.paid_at:
            steps.append((OrderStatus.PAID, order.paid_at))
        if order.cancelled_at:
            steps.append((OrderStatus.CANCELLED, order.cancelled_at))
        for payment in order.payments.all():
            steps += [(OrderStatus.REFUNDED, refund.created_at) for refund in payment.refunds.all()]
        when = serializers.DateTimeField()
        return [{"status": str(s), "at": when.to_representation(at)} for s, at in steps]

    def to_representation(self, order: Order) -> dict[str, Any]:
        data: dict[str, Any] = super().to_representation(order)
        user = self.context.get("user")
        hidden = (
            ("tax", "amount_due")
            if user and user.pk == order.seller_id
            else ("seller_share", "commission")
        )
        for name in hidden:
            data.pop(name)
        return data


class PaymentSerializer(serializers.Serializer[dict[str, Any]]):
    id = serializers.UUIDField()
    kind = serializers.CharField()
    amount = MoneySerializer()
    client_secret = serializers.CharField(help_text="For Stripe Elements in the browser.")


class PaymentStepSerializer(serializers.Serializer[dict[str, Any]]):
    """Confirm the payment in the browser; the order moves on only when Stripe confirms it."""

    order = OrderSerializer()
    payment = PaymentSerializer()
