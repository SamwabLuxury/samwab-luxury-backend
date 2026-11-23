"""python manage.py check_payments: proves the sandbox keys work with a $1 test payment."""

from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from django.test import override_settings


def run() -> str:
    out = StringIO()
    call_command("check_payments", stdout=out)
    return out.getvalue()


def test_it_makes_and_cancels_a_one_dollar_test_payment() -> None:
    with override_settings(PAYMENT_PROVIDER="fake"):
        output = run()

    assert "Created a 1.00 USD test payment" in output
    assert "cancelled it" in output
    assert "Payments are working" in output


@pytest.mark.parametrize("key", ["sk_live_abc", "rk_live_abc"])
def test_it_refuses_live_keys(key: str) -> None:
    with (
        override_settings(PAYMENT_PROVIDER="stripe", STRIPE_SECRET_KEY=key),
        pytest.raises(CommandError, match="live"),
    ):
        run()


def test_a_sandbox_key_that_happens_to_contain_live_is_not_refused() -> None:
    from apps.payments.management.commands.check_payments import is_live_key

    assert is_live_key("sk_live_abc") and is_live_key("rk_live_abc")
    assert not is_live_key("sk_test_live_demo")


def test_it_explains_a_missing_key() -> None:
    with (
        override_settings(PAYMENT_PROVIDER="stripe", STRIPE_SECRET_KEY=""),
        pytest.raises(CommandError, match="STRIPE_SECRET_KEY"),
    ):
        run()


def test_a_stripe_failure_is_explained(monkeypatch: pytest.MonkeyPatch) -> None:
    from apps.payments.management.commands import check_payments
    from apps.payments.providers.stripe import StripeProvider
    from apps.payments.tests.stripe_fakes import RecordingHTTPClient

    refusing = RecordingHTTPClient({"error": {"type": "invalid_request_error"}}, status=401)
    monkeypatch.setattr(
        check_payments,
        "get_provider",
        lambda: StripeProvider(secret_key="sk_test_bad", webhook_secret="", http_client=refusing),  # noqa: S106
    )

    with (
        override_settings(PAYMENT_PROVIDER="stripe", STRIPE_SECRET_KEY="sk_test_bad"),  # noqa: S106
        pytest.raises(CommandError, match="Check STRIPE_SECRET_KEY"),
    ):
        run()
