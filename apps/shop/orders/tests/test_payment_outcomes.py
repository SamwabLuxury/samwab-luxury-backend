"""What happens when the payment succeeds, fails, arrives twice, late, or for the wrong amount."""

import pytest
from django.utils import timezone

from apps.money.payments.providers import fake_provider
from apps.platform.audit.models import AuditEvent
from apps.shop.orders.models import Order
from apps.shop.orders.tests.helpers import place_order, stripe_says

pytestmark = pytest.mark.django_db


def test_a_successful_payment_marks_the_order_paid_and_the_listing_sold() -> None:
    order, _ = place_order()

    stripe_says(order, "succeeded")

    order.refresh_from_db()
    assert order.status == "paid"
    assert order.paid_at is not None
    assert order.listing.status == "sold"
    assert AuditEvent.objects.filter(action="orders.order.paid", object_id=order.pk).exists()


def test_a_declined_card_keeps_the_order_waiting_and_records_why() -> None:
    order, _ = place_order()

    stripe_says(
        order, "requires_payment_method", failure_reason="card_declined: Your card was declined."
    )

    order.refresh_from_db()
    payment = order.payments.get()
    assert order.status == "pending_payment"
    assert payment.status == "requires_payment_method"
    assert payment.failure_reason == "card_declined: Your card was declined."
    assert order.listing.status == "live"


def test_after_a_decline_another_card_on_the_same_payment_succeeds() -> None:
    order, _ = place_order()
    stripe_says(order, "requires_payment_method", failure_reason="card_declined")

    stripe_says(order, "succeeded")

    order.refresh_from_db()
    assert order.status == "paid"
    assert order.payments.count() == 1  # still the one payment


def test_the_same_news_twice_changes_nothing_the_second_time() -> None:
    order, _ = place_order()
    stripe_says(order, "succeeded")
    paid_at = Order.objects.get().paid_at

    stripe_says(order, "succeeded")

    assert Order.objects.get().paid_at == paid_at
    assert AuditEvent.objects.filter(action="orders.order.paid").count() == 1


def test_a_late_failure_never_undoes_a_success() -> None:
    order, _ = place_order()
    stripe_says(order, "succeeded")

    stripe_says(order, "requires_payment_method", failure_reason="card_declined")

    order.refresh_from_db()
    assert order.status == "paid"


def test_a_payment_for_the_wrong_amount_is_flagged_not_accepted(
    caplog: pytest.LogCaptureFixture,
) -> None:
    order, _ = place_order()

    stripe_says(order, "succeeded", amount_received=100)

    order.refresh_from_db()
    assert order.status == "pending_payment"
    assert order.payments.get().failure_reason == "amount_mismatch"
    assert "amount" in caplog.text.lower()


def test_money_arriving_after_the_order_was_cancelled_is_refunded() -> None:
    from apps.shop.orders import services

    order, _ = place_order()
    services.cancel_order(order, by=order.buyer)
    fake = fake_provider()
    payment = order.payments.get()

    stripe_says(order, "succeeded")  # the bank finished after all

    order.refresh_from_db()
    refund = payment.refunds.get()
    assert str(refund) == f"{refund.provider_refund_id} · missed_deadline"
    assert order.status == "refunded"
    assert (refund.amount_minor, refund.reason) == (order.total_minor, "missed_deadline")
    assert fake.refunds[refund.provider_refund_id].amount.amount_minor == order.total_minor


def test_money_for_a_listing_withdrawn_meanwhile_is_refunded() -> None:
    from apps.shop.listings import services as listings
    from apps.shop.listings.tests.helpers import make_admin
    from apps.shop.orders.models import Order as O

    order, _ = place_order()
    O.objects.filter(pk=order.pk).update(hold_until=timezone.now())  # the hold ran out
    listings.withdraw_listing(order.listing, by=make_admin())

    stripe_says(order, "succeeded")

    order.refresh_from_db()
    assert order.status == "refunded"
    assert order.cancel_reason == "listing_unavailable"
