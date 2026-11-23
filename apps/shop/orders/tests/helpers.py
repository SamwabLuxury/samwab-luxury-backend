"""Helpers for order tests: a buyer, a live listing, and placing an order."""

from typing import Any

from django.test import Client

from apps.money.payments.providers import fake_provider
from apps.shop.listings.models import Listing
from apps.shop.listings.tests.helpers import make_live_listing
from apps.shop.orders import services
from apps.shop.orders.models import Order
from apps.users.accounts.models import User
from apps.users.addresses.models import Address
from apps.users.addresses.tests.helpers import make_address, make_user

ORDERS = "/api/v1/orders/"


def buyer(email: str = "ada@example.com") -> User:
    return make_user(email)


def live_listing(**fields: Any) -> Listing:
    return make_live_listing(**fields)


def place_order(
    who: User | None = None, listing: Listing | None = None, **fields: Any
) -> tuple[Order, str]:
    """An order paid in full, kept in the vault: returns the order and the client secret."""
    fields.setdefault("delivery_choice", "keep_in_vault")
    return services.create_order(who or buyer(), listing or live_listing(), **fields)


def address_of(who: User) -> Address:
    return make_address(who)


def post_order(client: Client, body: dict[str, Any], key: str = "key-1") -> Any:
    return client.post(
        ORDERS, body, content_type="application/json", headers={"Idempotency-Key": key}
    )


def stripe_says(order: Order, status: str, **fields: Any) -> None:
    """Act as Stripe telling us about the order's payment (what the webhook does)."""
    payment = order.payments.get()
    fake_provider().set_status(payment.provider_payment_id, status, **fields)
    from apps.money.payments import services as payments

    payments.payment_changed(payment.provider_payment_id, source="test")
