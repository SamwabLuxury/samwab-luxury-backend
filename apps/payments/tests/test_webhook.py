"""POST /webhooks/stripe/: checked, stored once by event id, answered at once."""

from typing import Any

import pytest
from django.test import Client, override_settings

from apps.payments.models import StripeEvent
from apps.payments.tests.stripe_fakes import WEBHOOK_SECRET, event, signed

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.usefixtures("stripe_settings"),
]
URL = "/webhooks/stripe/"


@pytest.fixture
def stripe_settings() -> Any:
    with override_settings(
        PAYMENT_PROVIDER="stripe",
        STRIPE_SECRET_KEY="sk_test_only",  # noqa: S106 (made up)
        STRIPE_WEBHOOK_SECRET=WEBHOOK_SECRET,
    ):
        yield


def deliver(client: Client, body: bytes, header: str | None) -> Any:
    headers = {"Stripe-Signature": header} if header else None
    return client.post(URL, body, content_type="application/json", headers=headers)


def test_a_signed_event_is_stored_and_answered_200() -> None:
    body, header = signed(event())
    client = Client(enforce_csrf_checks=True)  # Stripe sends no CSRF token

    response = deliver(client, body, header)

    assert response.status_code == 200
    assert response.json() == {"received": True}
    stored = StripeEvent.objects.get()
    assert (stored.id, stored.type, stored.livemode) == (
        "evt_test_1",
        "payment_intent.succeeded",
        False,
    )
    assert stored.payload["data"]["object"]["id"] == "pi_test_123"
    assert stored.processed_at is None  # processing comes with orders (build E5)


def test_the_same_event_twice_is_stored_once(client: Client) -> None:
    body, header = signed(event())

    first, second = deliver(client, body, header), deliver(client, body, header)

    assert (first.status_code, second.status_code) == (200, 200)
    assert StripeEvent.objects.count() == 1


def test_a_bad_signature_is_a_400_and_nothing_is_stored(client: Client) -> None:
    body, _ = signed(event())
    _, wrong = signed(event(), secret="whsec_other")  # noqa: S106 (made up)

    for header in (wrong, None):
        response = deliver(client, body, header)
        assert response.status_code == 400
        assert response["Content-Type"] == "application/problem+json"
        assert response.json()["code"] == "webhook_signature_invalid"
    assert not StripeEvent.objects.exists()


def test_only_post_is_allowed(client: Client) -> None:
    assert client.get(URL).status_code == 405


def test_without_a_webhook_secret_every_event_is_refused(client: Client) -> None:
    body, header = signed(event())

    with override_settings(STRIPE_WEBHOOK_SECRET=""):
        response = deliver(client, body, header)

    assert response.status_code == 400
    assert not StripeEvent.objects.exists()


def test_the_table_is_named_as_in_the_data_model() -> None:
    assert str(StripeEvent(id="evt_1", type="charge.refunded")) == "evt_1 · charge.refunded"
    assert StripeEvent._meta.db_table == "stripe_events"
    assert StripeEvent._meta.pk is not None and StripeEvent._meta.pk.name == "id"
