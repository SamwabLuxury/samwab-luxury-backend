"""Acting on Stripe events: the webhook asks Stripe for the payment's latest state."""

from typing import Any

import pytest
from django.test import Client, override_settings

from apps.money.payments import services
from apps.money.payments.models import StripeEvent
from apps.money.payments.providers import fake_provider
from apps.money.payments.tests.stripe_fakes import event, payment_intent
from apps.shop.orders.models import Order
from apps.shop.orders.tests.helpers import place_order

pytestmark = pytest.mark.django_db
URL = "/webhooks/stripe/"


def deliver(client: Client, data: dict[str, Any]) -> Any:
    # The fake provider reads webhooks without a signature (signatures: test_webhook.py).
    import json

    return client.post(URL, json.dumps(data), content_type="application/json")


def about(order: Order, **fields: Any) -> dict[str, Any]:
    pid = order.payments.get().provider_payment_id
    return event(
        data={"object": payment_intent(id=pid, **fields)},
        **{k: v for k, v in fields.items() if k == "type"},
    )


def test_a_succeeded_event_marks_the_order_paid(client: Client) -> None:
    order, _ = place_order()
    fake_provider().set_status(order.payments.get().provider_payment_id, "succeeded")

    response = deliver(client, about(order))

    assert response.status_code == 200
    order.refresh_from_db()
    assert order.status == "paid"
    assert StripeEvent.objects.get().processed_at is not None


def test_the_state_comes_from_stripe_not_from_the_event(client: Client) -> None:
    order, _ = place_order()  # Stripe still says: waiting for a card

    deliver(client, about(order, status="succeeded"))  # an old or forged-looking body

    order.refresh_from_db()
    assert order.status == "pending_payment"


def test_events_for_payments_that_are_not_ours_are_stored_and_ignored(client: Client) -> None:
    response = deliver(client, event(data={"object": payment_intent(id="pi_from_the_dashboard")}))

    assert response.status_code == 200
    assert StripeEvent.objects.get().processed_at is not None


def test_other_event_types_are_stored_and_left_alone(client: Client) -> None:
    deliver(
        client,
        event(type="customer.created", data={"object": {"id": "cus_1", "object": "customer"}}),
    )

    assert StripeEvent.objects.get().processed_at is not None


def test_if_processing_fails_stripe_is_told_to_retry_and_the_retry_works(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    order, _ = place_order()
    fake_provider().set_status(order.payments.get().provider_payment_id, "succeeded")
    real = services.payment_changed

    def broken(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("database hiccup")

    monkeypatch.setattr(services, "payment_changed", broken)
    with override_settings(DEBUG_PROPAGATE_EXCEPTIONS=False):
        client.raise_request_exception = False
        first = deliver(client, about(order))
    stored = StripeEvent.objects.get()
    assert first.status_code == 500
    assert (stored.processed_at, stored.attempts) == (None, 1)
    assert "database hiccup" in stored.last_error

    monkeypatch.setattr(services, "payment_changed", real)
    retry = deliver(client, about(order))

    assert retry.status_code == 200
    order.refresh_from_db()
    assert order.status == "paid"
    stored.refresh_from_db()
    assert stored.attempts == 2 and stored.processed_at is not None


def test_the_client_secret_is_not_kept_in_stored_events(client: Client) -> None:
    deliver(client, event())

    deliver(
        client,
        event(id="evt_list", data={"object": {"id": "x", "items": [{"client_secret": "s"}]}}),
    )

    stored = StripeEvent.objects.get(id="evt_test_1").payload
    assert "client_secret" not in stored["data"]["object"]
    assert StripeEvent.objects.get(id="evt_list").payload["data"]["object"]["items"] == [{}]
    assert "secret" not in str(stored)
