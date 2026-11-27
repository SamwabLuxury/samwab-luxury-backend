"""Checkout asks for the terms of service and the returns policy (build 11).

Only texts in force count: until the owners publish their wording, checkout works as
before. Once a text is published, a buyer who has not accepted its current version is
refused before anything is saved, so no piece is held and no payment is started.
"""

import pytest
from django.test import Client, override_settings

from apps.money.payments.providers import fake_provider
from apps.shop.orders.exceptions import TermsNotAcceptedError
from apps.shop.orders.models import Order
from apps.shop.orders.tests.helpers import address_of, buyer, live_listing, place_order, post_order
from apps.users.legal.enums import DocumentKind
from apps.users.legal.tests.helpers import accept, publish

pytestmark = pytest.mark.django_db


def test_with_nothing_published_checkout_needs_no_acceptance() -> None:
    ada = buyer()

    order, _ = place_order(ada, shipping_address=address_of(ada))

    assert order.pk


def test_a_buyer_who_has_not_accepted_the_terms_is_refused() -> None:
    publish(DocumentKind.TERMS_OF_SERVICE)
    ada = buyer()
    listing = live_listing()

    with pytest.raises(TermsNotAcceptedError):
        place_order(ada, listing, shipping_address=address_of(ada))

    assert not Order.objects.exists()
    assert fake_provider().payments == {}
    listing.refresh_from_db()
    assert listing.status == "live"


def test_the_returns_policy_is_asked_for_too() -> None:
    accept(buyer(), publish(DocumentKind.TERMS_OF_SERVICE))
    publish(DocumentKind.RETURNS_POLICY)
    ada = buyer()

    with pytest.raises(TermsNotAcceptedError):
        place_order(ada, shipping_address=address_of(ada))


def test_after_accepting_both_she_can_pay() -> None:
    ada = buyer()
    accept(ada, publish(DocumentKind.TERMS_OF_SERVICE))
    accept(ada, publish(DocumentKind.RETURNS_POLICY))

    order, _ = place_order(ada, shipping_address=address_of(ada))

    assert order.pk


def test_the_privacy_policy_alone_does_not_block_checkout() -> None:
    publish(DocumentKind.PRIVACY_POLICY)
    ada = buyer()

    order, _ = place_order(ada, shipping_address=address_of(ada))

    assert order.pk


@override_settings(LEGAL_CHECKOUT_DOCUMENTS=[])
def test_the_list_of_texts_is_a_setting() -> None:
    publish(DocumentKind.TERMS_OF_SERVICE)
    ada = buyer()

    order, _ = place_order(ada, shipping_address=address_of(ada))

    assert order.pk


def test_the_api_answers_422_in_plain_words(client: Client) -> None:
    publish(DocumentKind.TERMS_OF_SERVICE)
    ada = buyer()
    client.force_login(ada)
    listing = live_listing()

    response = post_order(
        client,
        {
            "listing_id": str(listing.pk),
            "payment_option": "pay_in_full",
            "delivery_choice": "buyer_courier",
            "shipping_address_id": str(address_of(ada).pk),
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "terms_not_accepted"
    assert "accept" in response.json()["detail"]
