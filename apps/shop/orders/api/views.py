"""Orders: buy a piece, see my orders, cancel before paying. Login required."""

from typing import Any

from django.db.models import QuerySet
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.generics import ListAPIView
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.platform.core.exceptions import NotFoundError
from apps.platform.core.money import Money
from apps.platform.idempotency.api import idempotent
from apps.shop.listings.models import Listing
from apps.shop.orders import selectors, services
from apps.shop.orders.api.serializers import (
    OrderCreateSerializer,
    OrderSerializer,
    PaymentStepSerializer,
)
from apps.shop.orders.enums import OrderStatus
from apps.shop.orders.exceptions import ReservationNotAvailableError
from apps.shop.orders.models import Order
from apps.users.accounts.models import User


def _user(request: Request) -> User:
    return request.user  # type: ignore[return-value]


class OrderListView(ListAPIView):  # type: ignore[type-arg]
    serializer_class = OrderSerializer

    def get_serializer_context(self) -> dict[str, Any]:
        return {**super().get_serializer_context(), "user": self.request.user}

    def get_queryset(self) -> QuerySet[Order]:
        params = self.request.query_params
        role = params.get("role", "buyer")
        state = params.get("status", "")
        if role not in ("buyer", "seller") or (state and state not in OrderStatus.values):
            raise serializers.ValidationError(
                {"role" if role not in ("buyer", "seller") else "status": "Unknown value."}
            )
        return selectors.orders_of(_user(self.request), role=role, status=state)

    @extend_schema(
        summary="My orders, as buyer or seller",
        operation_id="orders_list",
        tags=["Orders"],
        parameters=[
            OpenApiParameter("role", enum=["buyer", "seller"], description="Default buyer."),
            OpenApiParameter("status", enum=OrderStatus.values),
        ],
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return super().get(request, *args, **kwargs)

    @extend_schema(
        summary="Buy a piece",
        description="Pay in full: returns the order and a Stripe PaymentIntent to confirm in "
        "the browser. The piece is held for 15 minutes (`pay_by`); the order is paid only "
        "when Stripe confirms it. 409 `listing_unavailable` if it is sold, withdrawn or "
        "another buyer is paying; 422 `reservation_not_available` for `reserve`; 502 "
        "`payment_provider_error` if Stripe cannot be reached (nothing is saved).",
        operation_id="orders_create",
        tags=["Orders"],
        request=OrderCreateSerializer,
        responses={201: PaymentStepSerializer},
    )
    @idempotent
    def post(self, request: Request) -> Response:
        user = _user(request)
        incoming = OrderCreateSerializer(data=request.data, context={"user": user})
        incoming.is_valid(raise_exception=True)
        data: dict[str, Any] = dict(incoming.validated_data)
        listing = Listing.objects.filter(pk=data.pop("listing_id")).first()
        if listing is None:
            raise NotFoundError("No such listing.")
        if data.pop("payment_option") == "reserve":
            raise ReservationNotAvailableError()
        order, client_secret = services.create_order(user, listing, **data)
        order = selectors.order_for(user, order.pk) or order
        payment = order.payments.get()
        step = {
            "order": order,
            "payment": {
                "id": payment.pk,
                "kind": payment.kind,
                "amount": Money(payment.amount_minor, payment.currency),
                "client_secret": client_secret,
            },
        }
        body = PaymentStepSerializer(step, context={"user": user, "request": request}).data
        return Response(body, status=status.HTTP_201_CREATED)


class OrderDetailView(APIView):
    @extend_schema(
        summary="Get an order",
        operation_id="orders_get",
        tags=["Orders"],
        responses=OrderSerializer,
    )
    def get(self, request: Request, id: str) -> Response:
        order = selectors.order_for(_user(request), id)
        if order is None:
            raise NotFoundError()
        return Response(
            OrderSerializer(order, context={"user": request.user, "request": request}).data
        )


class OrderCancelView(APIView):
    @extend_schema(
        summary="Cancel before payment",
        description="Only while waiting for payment (409 `order_not_cancellable`). If the "
        "payment went through at that moment, the order ends paid (409 `order_already_paid`).",
        operation_id="orders_cancel",
        tags=["Orders"],
        request=None,
        responses=OrderSerializer,
    )
    def post(self, request: Request, id: str) -> Response:
        user = _user(request)
        order = selectors.order_for(user, id)
        if order is None or order.buyer_id != user.pk:
            raise NotFoundError()
        services.cancel_order(order, by=user)
        fresh = selectors.order_for(user, id)
        return Response(OrderSerializer(fresh, context={"user": user, "request": request}).data)
