"""A drop's recap, and sold lots shown as sold (build E20).

Figma: "Drop 03 · Everyday Classics · Now in their hands · All eight pieces sold ·
What sold 8 of 8". Until now a closed drop answered with no lots, and a lot that sold
during a drop vanished from its page.

- A drop page lists its lots that are for sale **or sold** (each with ``status`` and
  ``sold_at``), in lot order. Withdrawn lots stay hidden. The early-hours rule is
  unchanged: before a viewer may see the lots, she sees none, sold or not.
- ``sold_count`` sits next to ``lot_count`` on every drop (list and page).
- ``GET /api/v1/drops/?phase=closed`` lists past drops, most recently closed first,
  for the home page's recap; without it the list is the running drops, as before.
"""

from typing import Any

import pytest
from django.test import Client

from apps.shop.listings import services
from apps.shop.listings.models import Listing
from apps.shop.listings.tests.helpers import make_admin
from apps.shop.listings.tests.test_drops import DROPS, logged_in, lot, make_drop, member

pytestmark = pytest.mark.django_db


def sell(listing: Listing) -> Listing:
    return services.mark_sold(listing)


def lots_of(page: dict[str, Any]) -> list[tuple[int, str]]:
    return [(row["lot_number"], row["status"]) for row in page["lots"]]


# ---------- the recap of a closed drop ----------


def test_a_closed_drop_shows_what_sold_and_what_did_not(client: Client) -> None:
    drop = make_drop("closed", name="Everyday Classics")
    sold_one = lot(drop, number=1)
    lot(drop, number=2)  # unsold: now also in the normal shop
    sell(sold_one)

    page = client.get(f"{DROPS}7/").json()

    assert page["phase"] == "closed"
    assert lots_of(page) == [(1, "sold"), (2, "live")]
    assert page["lots"][0]["sold_at"] is not None
    assert page["lots"][1]["sold_at"] is None
    assert page["lot_count"] == 2
    assert page["sold_count"] == 1


def test_all_lots_sold_reads_eight_of_eight(client: Client) -> None:
    drop = make_drop("closed")
    for number in range(1, 9):
        sell(lot(drop, number=number))

    page = client.get(f"{DROPS}7/").json()

    assert (page["sold_count"], page["lot_count"]) == (8, 8)
    assert [status for _, status in lots_of(page)] == ["sold"] * 8


def test_a_withdrawn_lot_is_left_out_of_the_recap(client: Client) -> None:
    drop = make_drop("closed")
    lot(drop, number=1)
    withdrawn = lot(drop, number=2)
    services.withdraw_listing(withdrawn, by=make_admin())

    page = client.get(f"{DROPS}7/").json()

    assert lots_of(page) == [(1, "live")]
    assert page["lot_count"] == 2  # how many it had, as before
    assert page["sold_count"] == 0


# ---------- sold lots while a drop runs ----------


def test_a_lot_that_sells_during_the_drop_stays_on_its_page_marked_sold(client: Client) -> None:
    drop = make_drop("open")
    sell(lot(drop, number=1))
    lot(drop, number=2)

    page = client.get(f"{DROPS}7/").json()

    assert lots_of(page) == [(1, "sold"), (2, "live")]
    assert page["sold_count"] == 1


def test_in_the_early_hours_only_members_see_lots_sold_or_not(client: Client) -> None:
    drop = make_drop("members")
    sell(lot(drop, number=1))
    lot(drop, number=2)

    assert client.get(f"{DROPS}7/").json()["lots"] == []
    assert lots_of(logged_in(member()).get(f"{DROPS}7/").json()) == [(1, "sold"), (2, "live")]


def test_before_early_access_nobody_sees_a_sold_lot(client: Client) -> None:
    drop = make_drop("upcoming")
    sell(lot(drop, number=1))

    assert logged_in(member()).get(f"{DROPS}7/").json()["lots"] == []


# ---------- the list of drops ----------


def test_the_list_still_shows_running_drops_with_their_sold_count(client: Client) -> None:
    running = make_drop("open", number=4)
    sell(lot(running, number=1))
    make_drop("closed", number=3)

    rows = client.get(DROPS).json()["results"]

    assert [(r["number"], r["sold_count"], r["lot_count"]) for r in rows] == [(4, 1, 1)]


def test_past_drops_are_listed_newest_first(client: Client) -> None:
    older = make_drop("closed", number=2)
    older.closes_at = older.closes_at.replace(year=older.closes_at.year - 1)
    older.public_at = older.public_at.replace(year=older.public_at.year - 1)
    older.save()
    make_drop("closed", number=3)
    make_drop("open", number=4)

    rows = client.get(DROPS, {"phase": "closed"}).json()["results"]

    assert [r["number"] for r in rows] == [3, 2]
    assert {r["phase"] for r in rows} == {"closed"}


def test_an_unknown_phase_is_refused(client: Client) -> None:
    response = client.get(DROPS, {"phase": "soon"})

    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"


def test_the_recap_costs_a_fixed_number_of_queries(
    client: Client, django_assert_max_num_queries: Any
) -> None:
    drop = make_drop("closed")
    for number in range(1, 7):
        listing = lot(drop, number=number)
        if number % 2:
            sell(listing)

    with django_assert_max_num_queries(8):  # the same budget as a running drop's page
        client.get(f"{DROPS}7/")
