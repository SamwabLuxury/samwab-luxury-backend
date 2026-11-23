"""Reading orders: my orders, one order, and the listing's hold in browse."""

from typing import Any

import pytest
from django.test import Client

from apps.orders.tests.helpers import ORDERS, buyer, place_order, stripe_says

pytestmark = pytest.mark.django_db


def test_i_see_only_my_orders(client: Client) -> None:
    mine, _ = place_order()
    place_order(buyer("chidi@example.com"))
    client.force_login(mine.buyer)

    response = client.get(ORDERS)

    assert response.status_code == 200
    assert [row["id"] for row in response.json()["results"]] == [str(mine.pk)]


def test_filter_by_status(client: Client) -> None:
    paid, _ = place_order()
    stripe_says(paid, "succeeded")
    from apps.listings.tests.helpers import make_live_listing

    waiting, _ = place_order(paid.buyer, make_live_listing())
    client.force_login(paid.buyer)

    assert [r["id"] for r in client.get(ORDERS, {"status": "paid"}).json()["results"]] == [
        str(paid.pk)
    ]
    assert [
        r["id"] for r in client.get(ORDERS, {"status": "pending_payment"}).json()["results"]
    ] == [str(waiting.pk)]


def test_the_seller_sees_their_sales_with_their_share(client: Client) -> None:
    order, _ = place_order()
    client.force_login(order.seller)

    [row] = client.get(ORDERS, {"role": "seller"}).json()["results"]

    assert row["seller_share"] == {"amount": order.total_minor, "currency": "USD"}
    assert row["commission"] == {"amount": 0, "currency": "USD"}
    assert "amount_due" not in row and "tax" not in row
    assert client.get(ORDERS).json()["results"] == []  # bought nothing


def test_one_order_and_its_timeline(client: Client) -> None:
    order, _ = place_order()
    stripe_says(order, "succeeded")
    client.force_login(order.buyer)

    body: dict[str, Any] = client.get(f"{ORDERS}{order.pk}/").json()

    assert body["status"] == "paid"
    assert body["amount_due"] == {"amount": 0, "currency": "USD"}
    assert [step["status"] for step in body["timeline"]] == ["pending_payment", "paid"]


def test_someone_elses_order_is_not_found(client: Client) -> None:
    order, _ = place_order()
    client.force_login(buyer("chidi@example.com"))

    assert client.get(f"{ORDERS}{order.pk}/").status_code == 404
    response = client.post(f"{ORDERS}{order.pk}/cancel/")
    assert response.status_code == 404


def test_cancel_through_the_api(client: Client) -> None:
    order, _ = place_order()
    client.force_login(order.buyer)

    response = client.post(f"{ORDERS}{order.pk}/cancel/")

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert client.post(f"{ORDERS}{order.pk}/cancel/").status_code == 409


def test_login_is_needed(client: Client) -> None:
    assert client.get(ORDERS).status_code == 401


def test_browse_shows_when_a_piece_is_held_by_a_checkout(client: Client) -> None:
    order, _ = place_order()

    row = client.get(f"/api/v1/listings/{order.listing_id}/").json()

    assert row["reserved_until"] is not None
    assert row["reserved_until"][:16] == order.hold_until.isoformat().replace("+00:00", "Z")[:16]


def test_unknown_filter_values_are_a_400(client: Client) -> None:
    client.force_login(buyer())

    for params, field in (({"role": "owner"}, "role"), ({"status": "lost"}, "status")):
        response = client.get(ORDERS, params)
        assert response.status_code == 400
        assert [e["field"] for e in response.json()["errors"]] == [field]


def test_str_shows_the_number_and_status() -> None:
    order, _ = place_order()

    assert str(order) == f"{order.order_number} · pending_payment"
    payment = order.payments.get()
    assert str(payment) == f"{payment.provider_payment_id} · requires_payment_method"
