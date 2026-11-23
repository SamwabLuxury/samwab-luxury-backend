"""The start-up checks for payment settings."""

from django.test import override_settings

from apps.payments.checks import check_payment_settings


def ids(**settings: str) -> list[str]:
    with override_settings(**settings):
        return [problem.id or "" for problem in check_payment_settings(None)]


def test_an_unknown_provider_is_an_error() -> None:
    assert ids(PAYMENT_PROVIDER="paypal") == ["payments.E001"]


def test_stripe_without_keys_is_a_warning_for_each_key() -> None:
    assert ids(PAYMENT_PROVIDER="stripe", STRIPE_SECRET_KEY="", STRIPE_WEBHOOK_SECRET="") == [
        "payments.W001",
        "payments.W001",
    ]


def test_stripe_with_keys_and_the_fake_pass() -> None:
    assert (
        ids(
            PAYMENT_PROVIDER="stripe",
            STRIPE_SECRET_KEY="sk_test_x",  # noqa: S106 (made up)
            STRIPE_WEBHOOK_SECRET="whsec_x",  # noqa: S106 (made up)
        )
        == []
    )
    assert ids(PAYMENT_PROVIDER="fake") == []
