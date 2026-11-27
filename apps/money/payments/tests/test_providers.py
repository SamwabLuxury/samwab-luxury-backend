"""The payment provider interface: Stripe, and the fake used by tests."""

from typing import Any

import pytest
from django.test import override_settings

from apps.money.payments.exceptions import (
    PaymentProviderError,
    TaxAddressError,
    WebhookSignatureError,
)
from apps.money.payments.providers import get_provider
from apps.money.payments.providers.base import ProviderPayment, TaxAddress, TaxQuote
from apps.money.payments.providers.fake import FakeProvider
from apps.money.payments.providers.stripe import StripeProvider
from apps.money.payments.tests.stripe_fakes import (
    WEBHOOK_SECRET,
    RecordingHTTPClient,
    event,
    payment_intent,
    signed,
)
from apps.platform.core.money import Money


def stripe_with(http: RecordingHTTPClient) -> StripeProvider:
    return StripeProvider(
        secret_key="sk_test_only",  # noqa: S106 (made up)
        webhook_secret=WEBHOOK_SECRET,
        http_client=http,
    )


def test_creating_a_payment_sends_stripe_the_amount_in_cents() -> None:
    http = RecordingHTTPClient()

    payment = stripe_with(http).create_payment(
        Money(1_250_000), reference="order-42", idempotency_key="key-1"
    )

    assert payment == ProviderPayment(
        id="pi_test_123",
        status="requires_payment_method",
        amount=Money(1_250_000),
        client_secret="pi_test_123_secret_abc",  # noqa: S106 (made up)
    )
    [call] = http.calls
    assert call["method"] == "post"
    assert call["url"].endswith("/v1/payment_intents")
    assert call["data"]["amount"] == ["1250000"]
    assert call["data"]["currency"] == ["usd"]
    assert call["data"]["automatic_payment_methods[enabled]"] == ["true"]
    assert call["data"]["metadata[reference]"] == ["order-42"]
    assert call["headers"]["Idempotency-Key"] == "key-1"
    assert call["headers"]["Authorization"] == "Bearer sk_test_only"


def test_reading_and_cancelling_a_payment() -> None:
    http = RecordingHTTPClient(payment_intent(status="canceled"))
    provider = stripe_with(http)

    assert provider.get_payment("pi_test_123").status == "canceled"
    assert provider.cancel_payment("pi_test_123").status == "canceled"
    assert http.calls[0]["url"].endswith("/v1/payment_intents/pi_test_123")
    assert http.calls[1]["url"].endswith("/v1/payment_intents/pi_test_123/cancel")


def test_a_stripe_failure_becomes_one_error_of_ours_without_the_key() -> None:
    http = RecordingHTTPClient(
        {
            "error": {
                "type": "invalid_request_error",
                "message": "Invalid API Key provided: sk_test_*nly",
            }
        },
        status=401,
    )

    with pytest.raises(PaymentProviderError) as failed:
        stripe_with(http).create_payment(Money(100), reference="x", idempotency_key="k")

    assert failed.value.status_code == 502
    assert failed.value.code == "payment_provider_error"
    assert "sk_test_only" not in str(failed.value)


def test_a_signed_webhook_is_read() -> None:
    body, header = signed(event())

    received = stripe_with(RecordingHTTPClient()).read_webhook(body, header)

    assert (received.id, received.type, received.livemode) == (
        "evt_test_1",
        "payment_intent.succeeded",
        False,
    )
    assert received.payload["data"]["object"]["id"] == "pi_test_123"


@pytest.mark.parametrize(
    "tamper",
    ["wrong_secret", "no_header", "changed_body", "too_old", "not_json"],
)
def test_a_webhook_that_fails_the_check_is_refused(tamper: str) -> None:
    body, header = signed(
        event(), secret="whsec_other" if tamper == "wrong_secret" else WEBHOOK_SECRET
    )
    if tamper == "changed_body":
        body = body.replace(b"succeeded", b"failed")
    if tamper == "too_old":
        body, header = signed(event(), at=1)
    if tamper == "not_json":  # correctly signed, but not an event
        body, header = _sign_raw(b"not json")

    with pytest.raises(WebhookSignatureError):
        stripe_with(RecordingHTTPClient()).read_webhook(
            body, None if tamper == "no_header" else header
        )


def _sign_raw(body: bytes) -> tuple[bytes, str]:
    import hashlib
    import hmac
    import time

    timestamp = int(time.time())
    digest = hmac.new(
        WEBHOOK_SECRET.encode(), f"{timestamp}.".encode() + body, hashlib.sha256
    ).hexdigest()
    return body, f"t={timestamp},v1={digest}"


def test_the_fake_provider_keeps_payments_in_memory() -> None:
    fake = FakeProvider()
    fake.fail_next = False

    made = fake.create_payment(Money(500), reference="order-1", idempotency_key="k1")
    again = fake.create_payment(Money(500), reference="order-1", idempotency_key="k1")

    assert made == again  # the same key gives the same payment, as Stripe does
    assert made.client_secret.startswith(made.id)
    assert fake.get_payment(made.id).status == "requires_payment_method"
    assert fake.cancel_payment(made.id).status == "canceled"


def test_the_fake_reads_webhooks_without_a_signature_check() -> None:
    received = FakeProvider().read_webhook(b'{"id": "evt_9", "type": "x", "livemode": false}', None)

    assert received.id == "evt_9"


def test_settings_choose_the_provider() -> None:
    with override_settings(PAYMENT_PROVIDER="fake"):
        assert isinstance(get_provider(), FakeProvider)
    with override_settings(
        PAYMENT_PROVIDER="stripe",
        STRIPE_SECRET_KEY="sk_test_x",  # noqa: S106 (made up)
        STRIPE_WEBHOOK_SECRET="whsec_x",  # noqa: S106 (made up)
    ):
        assert isinstance(get_provider(), StripeProvider)


def test_a_payment_reports_what_was_received_and_why_it_failed() -> None:
    http = RecordingHTTPClient(
        payment_intent(
            status="requires_payment_method",
            amount_received=0,
            last_payment_error={"code": "card_declined", "message": "Your card was declined."},
        )
    )

    payment = stripe_with(http).get_payment("pi_test_123")

    assert payment.amount_received == Money(0)
    assert payment.failure_reason == "card_declined: Your card was declined."


def test_refunding_sends_the_amount_and_our_key() -> None:
    http = RecordingHTTPClient(
        {"id": "re_1", "object": "refund", "amount": 500, "currency": "usd", "status": "succeeded"}
    )

    refund = stripe_with(http).refund_payment("pi_test_123", Money(500), idempotency_key="refund-1")

    assert (refund.id, refund.status, refund.amount) == ("re_1", "succeeded", Money(500))
    [call] = http.calls
    assert call["url"].endswith("/v1/refunds")
    assert call["data"]["payment_intent"] == ["pi_test_123"]
    assert call["data"]["amount"] == ["500"]
    assert call["headers"]["Idempotency-Key"] == "refund-1"


def test_a_refused_refund_becomes_our_error() -> None:
    http = RecordingHTTPClient(
        {"error": {"type": "invalid_request_error", "code": "charge_already_refunded"}}, status=400
    )

    with pytest.raises(PaymentProviderError):
        stripe_with(http).refund_payment("pi_test_123", Money(500), idempotency_key="refund-1")


# ---------- Sales tax (build E22): Stripe Tax calculations attached to the payment ----------

CHICAGO = TaxAddress(
    line1="233 S Wacker Dr",
    line2="",
    city="Chicago",
    state="IL",
    postal_code="60606",
    country="US",
)


def tax_calculation(**fields: Any) -> dict[str, Any]:
    return {
        "id": "taxcalc_test_1",
        "object": "tax.calculation",
        "amount_total": 1_598_625,
        "currency": "usd",
        "tax_amount_exclusive": 148_625,
        "tax_amount_inclusive": 0,
        **fields,
    }


def test_working_out_tax_sends_stripe_the_price_address_and_tax_code() -> None:
    http = RecordingHTTPClient(tax_calculation())

    quote = stripe_with(http).calculate_tax(
        Money(1_450_000),
        address=CHICAGO,
        reference="2611-0042",
        tax_code="txcd_99999999",
        idempotency_key="order-1-tax",
    )

    assert quote == TaxQuote(
        calculation_id="taxcalc_test_1", tax=Money(148_625), total=Money(1_598_625)
    )
    [call] = http.calls
    assert call["url"].endswith("/v1/tax/calculations")
    sent = call["data"]
    assert sent["currency"] == ["usd"]
    assert sent["line_items[0][amount]"] == ["1450000"]
    assert sent["line_items[0][reference]"] == ["2611-0042"]
    assert sent["line_items[0][tax_code]"] == ["txcd_99999999"]
    assert sent["line_items[0][tax_behavior]"] == ["exclusive"]  # tax on top of the price
    assert sent["customer_details[address_source]"] == ["shipping"]
    assert sent["customer_details[address][line1]"] == ["233 S Wacker Dr"]
    assert sent["customer_details[address][city]"] == ["Chicago"]
    assert sent["customer_details[address][state]"] == ["IL"]
    assert sent["customer_details[address][postal_code]"] == ["60606"]
    assert sent["customer_details[address][country]"] == ["US"]
    assert "customer_details[address][line2]" not in sent  # empty parts are not sent
    assert call["headers"]["Idempotency-Key"] == "order-1-tax"


def test_an_address_stripe_cannot_place_becomes_our_tax_address_error() -> None:
    http = RecordingHTTPClient(
        {
            "error": {
                "type": "invalid_request_error",
                "code": "customer_tax_location_invalid",
                "message": "We could not determine the customer's tax location.",
                "param": "customer_details[address]",
            }
        },
        status=400,
    )

    with pytest.raises(TaxAddressError):
        stripe_with(http).calculate_tax(
            Money(1_000), address=CHICAGO, reference="r", tax_code="t", idempotency_key="k"
        )


def test_any_other_tax_failure_is_the_usual_provider_error() -> None:
    http = RecordingHTTPClient(
        {"error": {"type": "invalid_request_error", "code": "tax_code_invalid", "message": "x"}},
        status=400,
    )

    with pytest.raises(PaymentProviderError):
        stripe_with(http).calculate_tax(
            Money(1_000), address=CHICAGO, reference="r", tax_code="t", idempotency_key="k"
        )


def test_a_payment_with_tax_carries_the_calculation_for_stripe_to_record() -> None:
    http = RecordingHTTPClient(payment_intent(amount=1_598_625))

    stripe_with(http).create_payment(
        Money(1_598_625),
        reference="2611-0042",
        idempotency_key="key-1",
        tax_calculation="taxcalc_test_1",
    )

    sent = http.calls[0]["data"]
    assert sent["amount"] == ["1598625"]
    assert sent["hooks[inputs][tax][calculation]"] == ["taxcalc_test_1"]


def test_a_payment_without_tax_sends_no_tax_hook() -> None:
    http = RecordingHTTPClient()

    stripe_with(http).create_payment(Money(1_000), reference="r", idempotency_key="k")

    assert not any(name.startswith("hooks") for name in http.calls[0]["data"])
