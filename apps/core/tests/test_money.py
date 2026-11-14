"""Tests for apps.core.money: whole cents only, never negative, never mixed currencies."""

import dataclasses
from typing import Any

import pytest

from apps.core.money import CurrencyMismatchError, Money, MoneyError


def other_currency(amount_minor: int) -> Money:
    """Build Money in a currency we do not support, to test the mixing rules.

    The normal constructor refuses it, so this skips the checks on purpose.
    """
    value = object.__new__(Money)
    object.__setattr__(value, "amount_minor", amount_minor)
    object.__setattr__(value, "currency", "EUR")
    return value


# ---------- creating ----------


def test_money_holds_cents_and_defaults_to_usd() -> None:
    price = Money(1250)

    assert price.amount_minor == 1250
    assert price.currency == "USD"


def test_zero_is_allowed() -> None:
    assert Money.zero() == Money(0)
    assert Money.zero().amount_minor == 0


def test_very_large_amounts_are_exact() -> None:
    huge = Money(10**18)

    assert (huge + Money(1)).amount_minor == 10**18 + 1


@pytest.mark.parametrize("bad_amount", [12.5, "1250", None, True, False, 1250.0])
def test_amount_must_be_a_whole_number(bad_amount: Any) -> None:
    with pytest.raises(MoneyError):
        Money(bad_amount)


def test_negative_amount_is_refused() -> None:
    with pytest.raises(MoneyError):
        Money(-1)


@pytest.mark.parametrize("bad_currency", ["NGN", "usd", "", "US", None])
def test_unsupported_currency_is_refused(bad_currency: Any) -> None:
    with pytest.raises(MoneyError):
        Money(100, bad_currency)


def test_money_cannot_be_changed_after_it_is_made() -> None:
    price = Money(1250)

    with pytest.raises(dataclasses.FrozenInstanceError):
        price.amount_minor = 1  # type: ignore[misc]


def test_equal_amounts_are_equal_and_usable_as_dictionary_keys() -> None:
    assert Money(500) == Money(500)
    assert Money(500) != Money(501)
    assert len({Money(500), Money(500), Money(501)}) == 2


def test_money_is_not_equal_to_a_plain_number() -> None:
    assert Money(500) != 500  # type: ignore[comparison-overlap]


# ---------- adding and subtracting ----------


def test_add() -> None:
    assert Money(1000) + Money(250) == Money(1250)


def test_subtract() -> None:
    assert Money(1000) - Money(250) == Money(750)
    assert Money(1000) - Money(1000) == Money.zero()


def test_subtracting_more_than_we_have_is_refused() -> None:
    with pytest.raises(MoneyError):
        Money(100) - Money(101)


def test_adding_a_plain_number_is_refused() -> None:
    with pytest.raises(MoneyError):
        Money(100) + 5  # type: ignore[operator]


def test_mixing_currencies_is_refused() -> None:
    with pytest.raises(CurrencyMismatchError):
        Money(100) + other_currency(100)
    with pytest.raises(CurrencyMismatchError):
        Money(100) - other_currency(50)


# ---------- comparing ----------


def test_comparisons() -> None:
    assert Money(100) < Money(101)
    assert Money(100) <= Money(100)
    assert Money(101) > Money(100)
    assert Money(100) >= Money(100)
    assert not Money(100) < Money(100)


def test_comparing_different_currencies_is_refused() -> None:
    with pytest.raises(CurrencyMismatchError):
        _ = Money(100) < other_currency(200)


def test_sorting_works() -> None:
    assert sorted([Money(300), Money(100), Money(200)]) == [Money(100), Money(200), Money(300)]


# ---------- share (percentages) ----------


@pytest.mark.parametrize(
    ("amount", "bps", "expected"),
    [
        (100_000, 2_500, 25_000),  # 25% commission on $1,000.00
        (100_000, 800, 8_000),  # 8% on $1,000.00
        (100_000, 5_000, 50_000),  # 50% reservation deposit
        (100_000, 0, 0),
        (100_000, 10_000, 100_000),
        (0, 2_500, 0),
        (10, 2_500, 3),  # 2.5 cents rounds up to 3
        (9, 2_500, 2),  # 2.25 cents rounds down to 2
        (1, 5_000, 1),  # 0.5 cents rounds up to 1
        (1, 4_999, 0),  # just under half a cent rounds down
        (333, 3_333, 111),  # 110.9889 cents rounds to 111
    ],
)
def test_share(amount: int, bps: int, expected: int) -> None:
    assert Money(amount).share(bps) == Money(expected)


@pytest.mark.parametrize("bad_bps", [-1, 10_001, 25.0, "2500", None, True])
def test_share_refuses_a_bad_rate(bad_bps: Any) -> None:
    with pytest.raises(MoneyError):
        Money(1000).share(bad_bps)


def test_commission_and_owner_share_add_up_to_the_price() -> None:
    price = Money(99_999)
    commission = price.share(2_500)
    owner_share = price - commission

    assert commission + owner_share == price


# ---------- split ----------


def test_split_in_two_equal_parts() -> None:
    assert Money(1000).split([1, 1]) == [Money(500), Money(500)]


def test_split_gives_the_leftover_cent_to_the_last_part() -> None:
    assert Money(100).split([1, 1, 1]) == [Money(33), Money(33), Money(34)]


def test_split_follows_the_weights() -> None:
    # Owner share of $750.00 across a $500 deposit and a $500 remainder.
    assert Money(75_000).split([50_000, 50_000]) == [Money(37_500), Money(37_500)]
    # Uneven payments: 30% then 70%.
    assert Money(75_001).split([30, 70]) == [Money(22_500), Money(52_501)]


@pytest.mark.parametrize(
    ("amount", "weights"),
    [
        (1, [1, 1, 1]),
        (0, [1, 2, 3]),
        (99_999, [3, 7]),
        (100, [0, 1]),
        (12_345, [1]),
        (10**15 + 7, [1, 1, 1, 1, 1, 1, 1]),
    ],
)
def test_split_parts_always_add_up_to_the_whole(amount: int, weights: list[int]) -> None:
    parts = Money(amount).split(weights)

    assert len(parts) == len(weights)
    assert sum(part.amount_minor for part in parts) == amount


def test_split_with_a_zero_weight_gives_that_part_nothing() -> None:
    assert Money(100).split([0, 1]) == [Money(0), Money(100)]


@pytest.mark.parametrize("bad_weights", [[], [0, 0], [-1, 2], [1.5, 1], ["1", 1], [True, 1]])
def test_split_refuses_bad_weights(bad_weights: Any) -> None:
    with pytest.raises(MoneyError):
        Money(100).split(bad_weights)


# ---------- showing ----------


@pytest.mark.parametrize(
    ("amount", "text"),
    [(1250, "12.50 USD"), (5, "0.05 USD"), (0, "0.00 USD"), (100_000, "1000.00 USD")],
)
def test_str(amount: int, text: str) -> None:
    assert str(Money(amount)) == text
