"""Sales tax at checkout (build E22; D46, D67, D69).

The owner's answers: tax is charged "the normal usual US way" (prices shown before
tax, tax added at checkout from the buyer's delivery address); the company is
registered in Illinois and files the tax itself; buyers outside the US pay no US
sales tax. Stripe Tax works the amount out (only where the company is registered)
and, because the calculation is attached to the payment, records the tax for filing
and reverses it on refunds.

``SALES_TAX_ENABLED`` stays off until Stripe Tax is set up; until then checkout is
exactly as before.
"""

from typing import Any

import pytest
from django.test import Client, override_settings

from apps.money.payments.providers import fake_provider
from apps.shop.orders.models import Order, OrderNumberCounter
from apps.shop.orders.tests.helpers import buyer, live_listing, place_order, post_order, stripe_says
from apps.users.addresses.tests.helpers import make_address

pytestmark = pytest.mark.django_db

TAX_ON = override_settings(SALES_TAX_ENABLED=True, SALES_TAX_CODE="txcd_99999999")


def chicago(who: Any) -> Any:
    return make_address(
        who,
        line1="233 S Wacker Dr",
        city="Chicago",
        region="IL",
        postal_code="60606",
        country="US",
    )


@pytest.fixture
def illinois_rate() -> None:
    """Act as Stripe Tax with an Illinois registration: 10.25% in Chicago."""
    fake_provider().tax_bps = {"US-IL": 1025}


def test_while_switched_off_checkout_is_unchanged() -> None:
    ada = buyer()
    order, _ = place_order(ada, live_listing(ask_minor=1_450_000), shipping_address=chicago(ada))

    assert order.tax_minor == 0
    assert order.total_minor == 1_450_000
    assert order.tax_calculation_id == ""
    assert fake_provider().calculations == {}
    payment = order.payments.get()
    assert fake_provider().linked_calculation(payment.provider_payment_id) == ""


@TAX_ON
def test_tax_is_added_on_top_of_the_price(illinois_rate: None) -> None:
    ada = buyer()
    order, _ = place_order(ada, live_listing(ask_minor=1_450_000), shipping_address=chicago(ada))

    assert order.item_minor == 1_450_000
    assert order.tax_minor == 148_625  # 10.25% of $14,500.00
    assert order.total_minor == 1_598_625
    assert order.payments.get().amount_minor == 1_598_625  # the buyer pays price plus tax


@TAX_ON
def test_the_calculation_is_attached_to_the_payment_so_stripe_records_it(
    illinois_rate: None,
) -> None:
    ada = buyer()
    order, _ = place_order(ada, live_listing(), shipping_address=chicago(ada))

    assert order.tax_calculation_id.startswith("taxcalc_fake_")
    payment = order.payments.get()
    assert fake_provider().linked_calculation(payment.provider_payment_id) == (
        order.tax_calculation_id
    )


@TAX_ON
def test_stripe_is_given_the_delivery_address_the_price_and_our_tax_code(
    illinois_rate: None,
) -> None:
    ada = buyer()
    order, _ = place_order(ada, live_listing(ask_minor=1_450_000), shipping_address=chicago(ada))

    asked = fake_provider().calculations[order.tax_calculation_id]
    assert asked["amount"].amount_minor == 1_450_000
    assert asked["address"].line1 == "233 S Wacker Dr"
    assert asked["address"].city == "Chicago"
    assert asked["address"].state == "IL"
    assert asked["address"].postal_code == "60606"
    assert asked["address"].country == "US"
    assert asked["reference"] == order.order_number
    assert asked["tax_code"] == "txcd_99999999"
    assert asked["idempotency_key"] == f"order-{order.pk}-tax"


@TAX_ON
def test_a_buyer_outside_the_us_pays_no_us_sales_tax(illinois_rate: None) -> None:
    ada = buyer()
    order, _ = place_order(
        ada, live_listing(ask_minor=1_450_000), shipping_address=make_address(ada)
    )

    assert order.tax_minor == 0  # Lagos: no registration there, so Stripe Tax answers 0
    assert order.total_minor == 1_450_000


@TAX_ON
def test_a_state_where_the_company_is_not_registered_pays_none(illinois_rate: None) -> None:
    ada = buyer()
    order, _ = place_order(
        ada,
        live_listing(ask_minor=1_450_000),
        shipping_address=make_address(
            ada, city="New York", region="NY", postal_code="10001", country="US"
        ),
    )

    assert order.tax_minor == 0


@TAX_ON
def test_the_checkout_answer_shows_the_tax(client: Client, illinois_rate: None) -> None:
    ada = buyer()
    client.force_login(ada)

    response = post_order(
        client,
        {
            "listing_id": str(live_listing(ask_minor=1_450_000).pk),
            "payment_option": "pay_in_full",
            "delivery_choice": "buyer_courier",
            "shipping_address_id": str(chicago(ada).pk),
        },
    )

    assert response.status_code == 201, response.content
    order = response.json()["order"]
    assert order["tax"] == {"amount": 148_625, "currency": "USD"}
    assert order["total"] == {"amount": 1_598_625, "currency": "USD"}
    assert order["amount_due"] == {"amount": 1_598_625, "currency": "USD"}


@TAX_ON
def test_an_address_stripe_cannot_place_is_a_clear_422_and_nothing_is_saved(
    client: Client, illinois_rate: None
) -> None:
    ada = buyer()
    client.force_login(ada)
    fake_provider().tax_location_invalid_next = True

    response = post_order(
        client,
        {
            "listing_id": str(live_listing().pk),
            "payment_option": "pay_in_full",
            "delivery_choice": "buyer_courier",
            "shipping_address_id": str(chicago(ada).pk),
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "tax_address_invalid"
    assert "ZIP" in response.json()["detail"]
    assert not Order.objects.exists()
    assert fake_provider().payments == {}  # no payment was started
    assert not OrderNumberCounter.objects.filter(last__gt=0).exists()  # number given back


@TAX_ON
def test_stripe_unreachable_while_working_out_tax_saves_nothing(
    client: Client, illinois_rate: None
) -> None:
    ada = buyer()
    client.force_login(ada)
    fake_provider().fail_next = True

    response = post_order(
        client,
        {
            "listing_id": str(live_listing().pk),
            "payment_option": "pay_in_full",
            "delivery_choice": "buyer_courier",
            "shipping_address_id": str(chicago(ada).pk),
        },
    )

    assert response.status_code == 502
    assert not Order.objects.exists()


@TAX_ON
def test_an_order_with_tax_is_paid_when_stripe_receives_price_plus_tax(
    illinois_rate: None,
) -> None:
    ada = buyer()
    order, _ = place_order(ada, live_listing(ask_minor=1_450_000), shipping_address=chicago(ada))

    stripe_says(order, "succeeded")  # Stripe received the full amount it was asked for

    order.refresh_from_db()
    assert order.status == "paid"


@TAX_ON
def test_tax_needs_an_address(illinois_rate: None) -> None:
    from apps.money.payments.exceptions import TaxAddressError

    with pytest.raises(TaxAddressError):
        place_order(buyer(), live_listing())  # no delivery address: nothing to tax from
    assert not Order.objects.exists()


@TAX_ON
def test_staff_see_the_tax_and_its_stripe_calculation_on_the_order(
    client: Client, illinois_rate: None
) -> None:
    from apps.shop.listings.tests.helpers import make_admin
    from apps.users.accounts.tests.helpers import admin_login

    admin_login(client, make_admin())
    ada = buyer()
    order, _ = place_order(ada, live_listing(ask_minor=1_450_000), shipping_address=chicago(ada))

    page = client.get(f"/admin/orders/order/{order.pk}/change/").content.decode()

    assert "1,486.25" in page  # sales tax, in dollars
    assert order.tax_calculation_id in page  # to look it up in Stripe's tax pages
