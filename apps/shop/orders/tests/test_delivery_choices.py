"""Which delivery choices a buyer may pick (D49 option A, the lead, 25 Nov).

For now the buyer's own courier collects the piece: "keep it in the vault" is
refused with 422 ``delivery_choice_not_available`` until it is switched on in
``DELIVERY_CHOICES_OFFERED``. Partner delivery was removed (D47).
"""

import pytest
from django.test import Client, override_settings

from apps.shop.orders import services
from apps.shop.orders.exceptions import DeliveryChoiceNotAvailableError
from apps.shop.orders.models import Order
from apps.shop.orders.tests.helpers import buyer, live_listing, place_order, post_order
from apps.users.addresses.tests.helpers import make_address

pytestmark = pytest.mark.django_db


def test_only_the_buyers_own_courier_is_offered_for_now() -> None:
    from django.conf import settings

    assert settings.DELIVERY_CHOICES_OFFERED == ["buyer_courier"]


def test_keeping_it_in_the_vault_is_refused_and_nothing_is_saved(client: Client) -> None:
    ada = buyer()
    client.force_login(ada)
    listing = live_listing()

    response = post_order(
        client,
        {
            "listing_id": str(listing.pk),
            "payment_option": "pay_in_full",
            "delivery_choice": "keep_in_vault",
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "delivery_choice_not_available"
    assert "courier" in response.json()["detail"]
    assert not Order.objects.exists()


def test_the_service_refuses_it_too_so_no_other_path_can_slip_through() -> None:
    with pytest.raises(DeliveryChoiceNotAvailableError):
        services.create_order(buyer(), live_listing(), delivery_choice="keep_in_vault")

    assert not Order.objects.exists()


def test_the_buyers_courier_still_works(client: Client) -> None:
    ada = buyer()
    client.force_login(ada)

    response = post_order(
        client,
        {
            "listing_id": str(live_listing().pk),
            "payment_option": "pay_in_full",
            "delivery_choice": "buyer_courier",
            "shipping_address_id": str(make_address(ada).pk),
        },
    )

    assert response.status_code == 201, response.content
    assert response.json()["order"]["delivery_choice"] == "buyer_courier"


@override_settings(DELIVERY_CHOICES_OFFERED=["buyer_courier", "keep_in_vault"])
def test_switching_it_on_is_one_setting() -> None:
    order, _ = place_order(delivery_choice="keep_in_vault")

    assert order.delivery_choice == "keep_in_vault"
