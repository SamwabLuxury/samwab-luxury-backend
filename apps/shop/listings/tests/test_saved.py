"""Save for later (D47, D51 #4: the lead, 25 Nov): a buyer saves pieces to her
account, so the list follows her to every device. Saving holds nothing. A piece
that sells or is withdrawn drops off the list by itself.

PUT /api/v1/me/saved/{listing_id}/ saves (doing it twice changes nothing),
DELETE unsaves, GET /api/v1/me/saved/ lists the pieces still for sale, the most
recently saved first.
"""

from typing import Any

import pytest
from django.db import IntegrityError, transaction
from django.test import Client, override_settings

from apps.inventory.pieces.models import Piece
from apps.shop.listings import services
from apps.shop.listings.models import Listing, SavedListing
from apps.shop.listings.tests.helpers import make_admin, make_listing, make_live_listing
from apps.users.addresses.tests.helpers import make_user

pytestmark = pytest.mark.django_db

SAVED = "/api/v1/me/saved/"


@pytest.fixture
def ada(client: Client) -> Client:
    client.force_login(make_user("ada@example.com"))
    return client


def save(client: Client, listing: Listing) -> Any:
    return client.put(f"{SAVED}{listing.pk}/")


def ids(response: Any) -> list[str]:
    return [row["id"] for row in response.json()["results"]]


def test_saving_a_piece_puts_it_on_my_list(ada: Client) -> None:
    listing = make_live_listing()

    response = save(ada, listing)

    assert response.status_code == 200, response.content
    assert response.json()["listing_id"] == str(listing.pk)
    assert response.json()["saved_at"]
    listed = ada.get(SAVED)
    assert listed.status_code == 200
    [card] = listed.json()["results"]
    assert card["id"] == str(listing.pk)
    assert card["piece"]["title"]
    assert card["ask"] == {"amount": listing.ask_minor, "currency": "USD"}
    assert card["saved_at"] == response.json()["saved_at"]
    assert "price_explainer" not in card  # a card, like the shop list


def test_saving_twice_keeps_one_row_and_the_first_time(ada: Client) -> None:
    listing = make_live_listing()

    first = save(ada, listing).json()
    again = save(ada, listing)

    assert again.status_code == 200
    assert again.json() == first
    assert SavedListing.objects.count() == 1


def test_newest_saved_comes_first(ada: Client) -> None:
    older, newer = make_live_listing(), make_live_listing()
    save(ada, older)
    save(ada, newer)

    assert ids(ada.get(SAVED)) == [str(newer.pk), str(older.pk)]


def test_unsaving_removes_it_and_is_safe_to_repeat(ada: Client) -> None:
    listing = make_live_listing()
    save(ada, listing)

    first = ada.delete(f"{SAVED}{listing.pk}/")
    again = ada.delete(f"{SAVED}{listing.pk}/")

    assert (first.status_code, again.status_code) == (204, 204)
    assert ada.get(SAVED).json()["results"] == []


def test_my_list_follows_me_to_another_device(ada: Client) -> None:
    listing = make_live_listing()
    save(ada, listing)

    phone = Client()
    phone.force_login(make_user("ada@example.com"))

    assert ids(phone.get(SAVED)) == [str(listing.pk)]


def test_each_person_sees_only_their_own_list(ada: Client) -> None:
    save(ada, make_live_listing())
    chidi = Client()
    chidi.force_login(make_user("chidi@example.com"))

    assert chidi.get(SAVED).json()["results"] == []


def test_a_withdrawn_or_sold_piece_drops_off_the_list(ada: Client) -> None:
    withdrawn, sold, still_live = make_live_listing(), make_live_listing(), make_live_listing()
    for listing in (withdrawn, sold, still_live):
        save(ada, listing)
    services.withdraw_listing(withdrawn, by=make_admin())
    Listing.objects.filter(pk=sold.pk).update(status="sold")

    assert ids(ada.get(SAVED)) == [str(still_live.pk)]


def test_a_piece_found_not_authentic_drops_off_too(ada: Client) -> None:
    listing = make_live_listing()
    save(ada, listing)
    Piece.objects.filter(pk=listing.piece_id).update(verification_status="not_authentic")

    assert ada.get(SAVED).json()["results"] == []


def test_only_pieces_for_sale_can_be_saved(ada: Client) -> None:
    draft = make_listing()
    unknown = "01a20786-8c65-76ee-b6de-bcf8976153ad"

    assert ada.put(f"{SAVED}{draft.pk}/").status_code == 404
    assert ada.put(f"{SAVED}{unknown}/").status_code == 404
    assert not SavedListing.objects.exists()


def test_saving_holds_nothing(ada: Client) -> None:
    listing = make_live_listing()
    save(ada, listing)

    card = Client().get(f"/api/v1/listings/{listing.pk}/").json()

    assert card["reserved_until"] is None


@override_settings(MAX_SAVED_LISTINGS=2)
def test_there_is_a_limit_per_account(ada: Client) -> None:
    first, second, third = make_live_listing(), make_live_listing(), make_live_listing()
    save(ada, first)
    save(ada, second)

    refused = save(ada, third)
    already_saved = save(ada, first)

    assert refused.status_code == 422
    assert refused.json()["code"] == "saved_limit_reached"
    assert already_saved.status_code == 200  # saving one again is not a new one


def test_login_is_required(client: Client) -> None:
    listing = make_live_listing()

    assert client.get(SAVED).status_code == 401
    assert client.put(f"{SAVED}{listing.pk}/").status_code == 401
    assert client.delete(f"{SAVED}{listing.pk}/").status_code == 401


def test_the_database_keeps_one_row_per_person_and_piece(ada: Client) -> None:
    listing = make_live_listing()
    save(ada, listing)
    row = SavedListing.objects.get()

    with pytest.raises(IntegrityError), transaction.atomic():
        SavedListing.objects.create(user=row.user, listing=listing)


def test_the_table_and_its_text(ada: Client) -> None:
    listing = make_live_listing()
    save(ada, listing)

    row = SavedListing.objects.get()

    assert SavedListing._meta.db_table == "saved_listings"
    assert str(row) == f"ada@example.com saved {listing}"


def test_the_list_costs_a_fixed_number_of_queries(
    ada: Client, django_assert_max_num_queries: Any
) -> None:
    for _ in range(5):
        save(ada, make_live_listing())

    with django_assert_max_num_queries(6):
        ada.get(SAVED)


def test_saving_from_two_devices_at_once_keeps_one_row(monkeypatch: pytest.MonkeyPatch) -> None:
    """The phone's save lands between the laptop's check and its insert."""
    ada_user = make_user("ada@example.com")
    listing = make_live_listing()
    phone_save = SavedListing.objects.create(user=ada_user, listing=listing)
    real_filter = SavedListing.objects.filter
    calls = {"n": 0}

    def first_check_misses(*args: Any, **kwargs: Any) -> Any:
        calls["n"] += 1
        found = real_filter(*args, **kwargs)
        return found.none() if calls["n"] == 1 else found

    monkeypatch.setattr(SavedListing.objects, "filter", first_check_misses)

    saved = services.save_listing(ada_user, listing.pk)

    assert saved == phone_save
    assert SavedListing.objects.count() == 1
