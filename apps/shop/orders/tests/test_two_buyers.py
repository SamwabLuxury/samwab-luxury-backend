"""Two buyers press "Buy" on the same piece at the same moment (PostgreSQL only:
SQLite cannot run two writers at once)."""

import threading

import pytest
from django.db import connection
from django.test import Client

from apps.shop.orders.models import Order
from apps.shop.orders.tests.helpers import buyer, live_listing, post_order


@pytest.mark.skipif(connection.vendor != "postgresql", reason="needs real concurrent connections")
@pytest.mark.django_db(transaction=True)
def test_only_one_of_two_buyers_at_the_same_moment_gets_the_piece() -> None:
    listing = live_listing()
    people = [buyer("ada@example.com"), buyer("chidi@example.com")]
    answers: list[int] = []
    start = threading.Barrier(2)

    def press_buy(who_email: str) -> None:
        client = Client()
        client.force_login(next(p for p in people if p.email == who_email))
        start.wait()
        body = {
            "listing_id": str(listing.pk),
            "payment_option": "pay_in_full",
            "delivery_choice": "keep_in_vault",
        }
        answers.append(post_order(client, body, key=f"k-{who_email}").status_code)
        connection.close()

    threads = [threading.Thread(target=press_buy, args=(p.email,)) for p in people]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(answers) == [201, 409]
    assert Order.objects.count() == 1
