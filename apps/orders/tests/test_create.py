"""Placing an order (POST /api/v1/orders/): one order, one payment, the right amount."""

from typing import Any

import pytest
from django.test import Client

from apps.addresses.tests.helpers import make_address
from apps.listings.models import Listing
from apps.listings.tests.helpers import make_admin, make_listing
from apps.orders.models import Order
from apps.orders.tests.helpers import address_of, buyer, live_listing, post_order
from apps.payments.models import Payment
from apps.payments.providers import fake_provider

pytestmark = pytest.mark.django_db


@pytest.fixture
def ada_client(client: Client) -> Client:
    client.force_login(buyer())
    return client


def body(listing: Listing, **fields: Any) -> dict[str, Any]:
    return {
        "listing_id": str(listing.pk),
        "payment_option": "pay_in_full",
        "delivery_choice": "keep_in_vault",
        **fields,
    }


def test_an_order_returns_the_payment_step_from_the_contract(ada_client: Client) -> None:
    listing = live_listing(ask_minor=1_250_000)

    response = post_order(ada_client, body(listing, acquisition_source="social"))

    assert response.status_code == 201, response.content
    step = response.json()
    order, payment = step["order"], step["payment"]
    assert order["status"] == "pending_payment"
    assert order["kind"] == "house_sale"
    assert order["channel"] == "buy_now"
    assert order["listing_id"] == str(listing.pk)
    assert order["order_number"].startswith("SW-")
    assert (
        order["item"]
        == order["total"]
        == order["amount_due"]
        == {"amount": 1_250_000, "currency": "USD"}
    )
    assert order["tax"] == {"amount": 0, "currency": "USD"}
    assert order["pay_by"]  # the 15-minute hold
    assert order["piece"]["title"] == "Kelly 28, Gold Togo"
    assert payment["kind"] == "full"
    assert payment["amount"] == {"amount": 1_250_000, "currency": "USD"}
    assert payment["client_secret"].startswith("pi_fake_")
    saved = Order.objects.get()
    assert (saved.buyer.email, saved.seller_id) == ("ada@example.com", listing.seller_id)
    assert saved.acquisition_source == "social"


def test_the_amount_comes_from_the_listing_never_from_the_request(ada_client: Client) -> None:
    listing = live_listing(ask_minor=1_250_000)

    response = post_order(ada_client, body(listing, total={"amount": 1, "currency": "USD"}, item=1))

    assert response.json()["payment"]["amount"]["amount"] == 1_250_000


def test_the_same_key_twice_gives_one_order_and_one_payment(ada_client: Client) -> None:
    listing = live_listing()

    first = post_order(ada_client, body(listing), key="same")
    again = post_order(ada_client, body(listing), key="same")

    assert (first.status_code, again.status_code) == (201, 201)
    assert again["Idempotent-Replayed"] == "true"
    assert again.json()["order"]["id"] == first.json()["order"]["id"]
    assert Order.objects.count() == Payment.objects.count() == 1
    assert len(fake_provider().payments) == 1


def test_one_order_asks_stripe_for_exactly_one_payment_with_its_own_key(ada_client: Client) -> None:
    post_order(ada_client, body(live_listing()))

    order = Order.objects.get()
    payment = order.payments.get()
    assert payment.idempotency_key == f"order-{order.pk}-full"
    assert payment.kind == "full"
    assert payment.amount_minor == order.total_minor


def test_a_second_order_for_the_same_piece_is_refused(client: Client) -> None:
    listing = live_listing()
    client.force_login(buyer())
    post_order(client, body(listing), key="a")
    client.force_login(buyer("chidi@example.com"))

    response = post_order(client, body(listing), key="b")

    assert response.status_code == 409
    assert response.json()["code"] == "listing_unavailable"
    assert Order.objects.count() == 1


@pytest.mark.parametrize("state", ["draft", "withdrawn"])
def test_a_listing_that_is_not_live_cannot_be_bought(ada_client: Client, state: str) -> None:
    from apps.listings import services as listings

    listing = make_listing()
    if state == "withdrawn":
        listings.withdraw_listing(listing, by=make_admin())

    response = post_order(ada_client, body(listing))

    assert response.status_code == 409
    assert response.json()["code"] == "listing_unavailable"


def test_an_unknown_listing_is_a_404(ada_client: Client) -> None:
    response = post_order(
        ada_client, {**body(live_listing()), "listing_id": "01a20786-8c65-76ee-b6de-bcf8976153ad"}
    )

    assert response.status_code == 404


def test_reserving_is_not_open_yet(ada_client: Client) -> None:
    response = post_order(ada_client, body(live_listing(), payment_option="reserve"))

    assert response.status_code == 422
    assert response.json()["code"] == "reservation_not_available"


def test_staff_cannot_buy_their_own_house_stock(client: Client) -> None:
    listing = live_listing()
    client.force_login(listing.seller)

    response = post_order(client, body(listing))

    assert response.status_code == 422
    assert response.json()["code"] == "cannot_buy_own_listing"


def test_courier_delivery_needs_one_of_my_addresses(ada_client: Client) -> None:
    listing = live_listing()

    missing = post_order(ada_client, body(listing, delivery_choice="buyer_courier"), key="1")
    someone_elses = make_address(buyer("chidi@example.com"))
    theirs = post_order(
        ada_client,
        body(listing, delivery_choice="buyer_courier", shipping_address_id=str(someone_elses.pk)),
        key="2",
    )

    assert missing.status_code == 400
    assert [e["field"] for e in missing.json()["errors"]] == ["shipping_address_id"]
    assert theirs.status_code == 400
    assert not Order.objects.exists()


def test_the_delivery_address_is_copied_onto_the_order_encrypted(ada_client: Client) -> None:
    from apps.orders.tests.helpers import buyer as get_buyer

    address = address_of(get_buyer())
    response = post_order(
        ada_client,
        body(live_listing(), delivery_choice="buyer_courier", shipping_address_id=str(address.pk)),
    )

    assert response.status_code == 201, response.content
    order = Order.objects.get()
    assert "12 Admiralty Way" in (order.shipping_address or "")
    address.line1 = "changed later"
    address.save()
    order.refresh_from_db()
    assert "12 Admiralty Way" in (order.shipping_address or "")  # a snapshot, not a link


def test_if_stripe_cannot_be_reached_nothing_is_saved(ada_client: Client) -> None:
    fake_provider().fail_next = True

    response = post_order(ada_client, body(live_listing()))

    assert response.status_code == 502
    assert response.json()["code"] == "payment_provider_error"
    assert not Order.objects.exists()
    assert not Payment.objects.exists()


def test_login_and_the_idempotency_key_are_required(client: Client) -> None:
    listing = live_listing()
    assert (
        client.post("/api/v1/orders/", body(listing), content_type="application/json").status_code
        == 401
    )
    client.force_login(buyer())

    response = client.post("/api/v1/orders/", body(listing), content_type="application/json")

    assert response.status_code == 400
    assert response.json()["code"] == "idempotency_key_missing"
