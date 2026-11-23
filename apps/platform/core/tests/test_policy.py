"""Tests for apps.platform.core.policy.

These pin the agreed values. If a number changes, this test fails, which makes
the change a deliberate one that shows up in review.
"""

from datetime import timedelta

from apps.platform.core import policy
from apps.platform.core.money import BPS_DENOMINATOR


def test_reservation_window_is_60_minutes() -> None:
    assert timedelta(minutes=60) == policy.RESERVATION_WINDOW


def test_return_window_is_24_hours() -> None:
    assert timedelta(hours=24) == policy.RETURN_WINDOW


def test_vault_trade_holding_period_is_7_days() -> None:
    assert timedelta(days=7) == policy.VAULT_TRADE_HOLDING_PERIOD


def test_default_reservation_deposit_is_50_percent() -> None:
    assert policy.DEFAULT_RESERVATION_DEPOSIT_BPS == 5_000


def test_deposit_rate_is_a_valid_rate() -> None:
    assert 0 < policy.DEFAULT_RESERVATION_DEPOSIT_BPS <= BPS_DENOMINATOR
