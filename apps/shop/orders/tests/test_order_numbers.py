"""Order numbers like 2611-0042: year and month, then a count that restarts every
month (D46, D51 #3: the lead, 25 Nov). The month is the UTC month.

Numbers come from one counter row per month, locked while an order is placed, so
two orders never share a number. A checkout that fails (Stripe unreachable) rolls
the count back with everything else, so failures leave no gaps.
"""

import threading
from datetime import UTC, datetime

import pytest
from django.db import IntegrityError, connection, transaction
from django.test import Client

from apps.money.payments.exceptions import PaymentProviderError
from apps.money.payments.providers import fake_provider
from apps.shop.orders.models import Order, OrderNumberCounter
from apps.shop.orders.numbers import next_order_number
from apps.shop.orders.tests.helpers import buyer, live_listing, place_order, post_order
from apps.users.addresses.tests.helpers import make_address

pytestmark = pytest.mark.django_db

NOV = datetime(2026, 11, 25, 14, 0, tzinfo=UTC)
DEC = datetime(2026, 12, 1, 0, 0, tzinfo=UTC)


def test_numbers_count_up_within_a_month() -> None:
    with transaction.atomic():
        numbers = [next_order_number(NOV) for _ in range(3)]

    assert numbers == ["2611-0001", "2611-0002", "2611-0003"]


def test_the_count_restarts_every_month_and_each_month_keeps_its_own() -> None:
    with transaction.atomic():
        november = [next_order_number(NOV), next_order_number(NOV)]
        december = next_order_number(DEC)
        late_november = next_order_number(NOV)

    assert november == ["2611-0001", "2611-0002"]
    assert december == "2612-0001"
    assert late_november == "2611-0003"


def test_the_month_is_the_utc_month() -> None:
    lagos_new_year = datetime.fromisoformat("2027-01-01T00:30:00+01:00")  # still 2026 in UTC

    with transaction.atomic():
        assert next_order_number(lagos_new_year) == "2612-0001"


def test_after_9999_the_count_simply_grows() -> None:
    OrderNumberCounter.objects.create(month="2611", last=9_999)

    with transaction.atomic():
        assert next_order_number(NOV) == "2611-10000"


def test_a_real_order_gets_this_months_number() -> None:
    order, _ = place_order()

    assert order.order_number == f"{order.created_at:%y%m}-0001"
    assert place_order(listing=live_listing())[0].order_number.endswith("-0002")


def test_a_failed_checkout_does_not_use_up_a_number() -> None:
    fake_provider().fail_next = True
    with pytest.raises(PaymentProviderError):
        place_order()

    order, _ = place_order()

    assert order.order_number.endswith("-0001")


def test_the_api_shows_the_new_number(client: Client) -> None:
    ada = buyer()
    client.force_login(ada)

    response = post_order(
        client,
        {
            "listing_id": str(live_listing().pk),
            "payment_option": "pay_in_full",
            "delivery_choice": "buyer_courier",
            "shipping_address_id": str(make_address(ada).pk),
        },
    )

    number = response.json()["order"]["order_number"]
    assert len(number) == 9 and number[4] == "-" and number.endswith("-0001"), number


def test_the_database_refuses_a_second_counter_for_a_month() -> None:
    OrderNumberCounter.objects.create(month="2611", last=1)

    with pytest.raises(IntegrityError), transaction.atomic():
        OrderNumberCounter.objects.create(month="2611", last=5)


@pytest.mark.skipif(connection.vendor != "postgresql", reason="needs real concurrent connections")
@pytest.mark.django_db(transaction=True)
def test_orders_placed_at_the_same_moment_get_different_numbers() -> None:
    listings = [live_listing() for n in range(4)]
    people = [buyer(f"buyer{n}@example.com") for n in range(4)]
    start = threading.Barrier(4)
    failures: list[BaseException] = []

    def buy(n: int) -> None:
        try:
            start.wait()
            place_order(people[n], listings[n])
        except BaseException as error:  # pragma: no cover - reported below
            failures.append(error)
        finally:
            connection.close()

    threads = [threading.Thread(target=buy, args=(n,)) for n in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert failures == []
    numbers = sorted(Order.objects.values_list("order_number", flat=True))
    assert [n[-4:] for n in numbers] == ["0001", "0002", "0003", "0004"]


def test_a_counter_reads_as_its_month_and_count() -> None:
    assert str(OrderNumberCounter(month="2611", last=42)) == "2611: 42"
