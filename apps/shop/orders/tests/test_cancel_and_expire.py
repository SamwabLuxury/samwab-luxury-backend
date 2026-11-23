"""Leaving checkout: the buyer cancels, or the 15-minute hold runs out."""

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.money.payments.providers import fake_provider
from apps.platform.core.exceptions import ConflictError
from apps.shop.orders import services
from apps.shop.orders.models import Order
from apps.shop.orders.tests.helpers import buyer, place_order, stripe_says

pytestmark = pytest.mark.django_db


def expire_hold(order: Order) -> None:
    Order.objects.filter(pk=order.pk).update(hold_until=timezone.now() - timedelta(seconds=1))


def test_the_hold_is_fifteen_minutes() -> None:
    before = timezone.now()

    order, _ = place_order()

    assert (
        before + timedelta(minutes=15) <= order.hold_until <= timezone.now() + timedelta(minutes=15)
    )


def test_cancelling_frees_the_piece_and_cancels_the_payment() -> None:
    order, _ = place_order()

    services.cancel_order(order, by=order.buyer)

    order.refresh_from_db()
    assert (order.status, order.cancel_reason) == ("cancelled", "buyer_cancelled")
    assert (
        fake_provider().get_payment(order.payments.get().provider_payment_id).status == "canceled"
    )
    again, _ = place_order(buyer("chidi@example.com"), order.listing)
    assert again.status == "pending_payment"


def test_a_paid_order_cannot_be_cancelled() -> None:
    order, _ = place_order()
    stripe_says(order, "succeeded")

    with pytest.raises(ConflictError) as refused:
        services.cancel_order(order, by=order.buyer)

    assert refused.value.code == "order_not_cancellable"


def test_cancelling_while_the_payment_quietly_succeeded_ends_paid() -> None:
    order, _ = place_order()
    fake_provider().set_status(
        order.payments.get().provider_payment_id, "succeeded"
    )  # webhook not here yet

    with pytest.raises(ConflictError) as refused:
        services.cancel_order(order, by=order.buyer)

    assert refused.value.code == "order_already_paid"
    order.refresh_from_db()
    assert order.status == "paid"


def test_an_expired_hold_is_released_when_the_next_buyer_arrives() -> None:
    order, _ = place_order()
    expire_hold(order)

    second, _ = place_order(buyer("chidi@example.com"), order.listing)

    order.refresh_from_db()
    assert (order.status, order.cancel_reason) == ("cancelled", "hold_expired")
    assert second.status == "pending_payment"


def test_an_expired_hold_that_was_actually_paid_stays_paid() -> None:
    order, _ = place_order()
    expire_hold(order)
    fake_provider().set_status(order.payments.get().provider_payment_id, "succeeded")

    with pytest.raises(ConflictError):
        place_order(buyer("chidi@example.com"), order.listing)

    order.refresh_from_db()
    assert order.status == "paid"


def test_the_expire_command_releases_every_stale_hold() -> None:
    from apps.shop.listings.tests.helpers import make_live_listing

    stale, _ = place_order()
    fresh, _ = place_order(buyer("chidi@example.com"), make_live_listing())
    expire_hold(stale)

    call_command("expire_orders", verbosity=0)

    stale.refresh_from_db()
    fresh.refresh_from_db()
    assert (stale.status, fresh.status) == ("cancelled", "pending_payment")


def test_the_reconcile_command_catches_a_missed_webhook() -> None:
    order, _ = place_order()
    fake_provider().set_status(
        order.payments.get().provider_payment_id, "succeeded"
    )  # no webhook came

    call_command("reconcile_payments", verbosity=0)

    order.refresh_from_db()
    assert order.status == "paid"


def test_only_the_buyer_may_cancel() -> None:
    from apps.platform.core.exceptions import NotFoundError

    order, _ = place_order()

    with pytest.raises(NotFoundError):
        services.cancel_order(order, by=buyer("chidi@example.com"))


def test_if_stripe_cannot_cancel_and_it_was_not_paid_the_order_stays_waiting() -> None:
    from apps.money.payments.exceptions import PaymentProviderError

    order, _ = place_order()
    fake_provider().fail_next = True  # the cancel call fails; Stripe still says "waiting"

    with pytest.raises(PaymentProviderError):
        services.cancel_order(order, by=order.buyer)

    order.refresh_from_db()
    assert order.status == "pending_payment"


def test_a_listing_cannot_be_withdrawn_while_a_checkout_holds_it() -> None:
    from apps.shop.listings import services as listings
    from apps.shop.listings.tests.helpers import make_admin

    order, _ = place_order()

    with pytest.raises(ConflictError) as refused:
        listings.withdraw_listing(order.listing, by=make_admin())

    assert refused.value.code == "listing_held"
