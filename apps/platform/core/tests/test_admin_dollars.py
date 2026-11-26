"""Staff type prices in dollars in the admin; the database keeps US cents (build E16).

A price typed in cents is easy to get wrong by a factor of 100, so every money box
in the admin reads and shows dollars, such as 12,500.00.
"""

import pytest
from django import forms
from django.test import Client

from apps.platform.core.admin_dollars import DollarsField


@pytest.mark.parametrize(
    ("typed", "cents"),
    [
        ("12,500.00", 1_250_000),
        ("12500", 1_250_000),
        ("$12,500.50", 1_250_050),
        (" 12500.5 ", 1_250_050),
        ("0.99", 99),
        ("0", 0),
    ],
)
def test_dollars_typed_in_any_usual_way_are_stored_as_cents(typed: str, cents: int) -> None:
    assert DollarsField().clean(typed) == cents


@pytest.mark.parametrize(
    ("typed", "message"),
    [
        ("12.345", "at most two digits after the point"),
        ("ten", "Enter an amount in dollars, such as 12,500.00."),
        ("-5", "cannot be below zero"),
        ("1,2,3.4.5", "Enter an amount in dollars, such as 12,500.00."),
    ],
)
def test_a_wrong_amount_says_what_to_type(typed: str, message: str) -> None:
    with pytest.raises(forms.ValidationError, match=message):
        DollarsField().clean(typed)


def test_an_empty_box_is_allowed_only_when_the_price_is_optional() -> None:
    assert DollarsField(required=False).clean("") is None
    with pytest.raises(forms.ValidationError):
        DollarsField().clean("")


def test_stored_cents_are_shown_as_dollars() -> None:
    field = DollarsField()
    assert field.prepare_value(1_250_000) == "12,500.00"
    assert field.prepare_value(99) == "0.99"
    assert field.prepare_value(None) == ""
    assert field.prepare_value("12,500.00") == "12,500.00"  # a re-shown form keeps the text


@pytest.mark.django_db
def test_the_listing_page_shows_dollars(client: Client) -> None:
    from apps.shop.listings.tests.helpers import make_admin, make_live_listing
    from apps.users.accounts.tests.helpers import admin_login

    admin_login(client, make_admin())
    listing = make_live_listing(ask_minor=1_250_000)

    page = client.get(f"/admin/listings/listing/{listing.pk}/change/").content.decode()

    assert 'value="12,500.00"' in page
    assert "In US dollars, such as 12,500.00." in page
    assert "cents" not in page.lower()


def test_the_dollar_box_is_drawn_like_every_other_box_with_a_dollar_sign() -> None:
    from unfold.widgets import UnfoldAdminTextInputWidget

    field = DollarsField()

    assert isinstance(field.widget, UnfoldAdminTextInputWidget)
    assert "$" in field.widget.render("ask", 1_250_000)


@pytest.mark.django_db
def test_order_screens_show_dollars_not_cents(client: Client) -> None:
    from apps.shop.listings.tests.helpers import make_admin
    from apps.shop.orders.tests.helpers import place_order
    from apps.users.accounts.tests.helpers import admin_login

    admin_login(client, make_admin())
    order, _ = place_order()
    total = f"{order.total_minor // 100:,}.{order.total_minor % 100:02d}"

    listing_page = client.get("/admin/orders/order/").content.decode()
    order_page = client.get(f"/admin/orders/order/{order.pk}/change/").content.decode()

    assert f"${total}" in listing_page
    assert f"${total}" in order_page
    for page in (listing_page, order_page):
        assert f">{order.total_minor}<" not in page.replace(" ", "").replace("\n", "")


@pytest.mark.django_db
def test_a_price_staff_cannot_change_is_shown_in_dollars(client: Client) -> None:
    from apps.shop.listings.tests.helpers import make_live_listing
    from apps.users.accounts import roles
    from apps.users.accounts.tests.helpers import admin_login, make_staff

    admin_login(client, make_staff("owner@samwab.com", roles.FINANCE))  # finance only look
    listing = make_live_listing(ask_minor=1_250_000)

    page = client.get(f"/admin/listings/listing/{listing.pk}/change/").content.decode()

    assert "$12,500.00" in page
    assert "1250000" not in page
