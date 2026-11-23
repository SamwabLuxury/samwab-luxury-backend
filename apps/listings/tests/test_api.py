"""The public browse API: GET /api/v1/listings/ and GET /api/v1/listings/{id}/."""

from typing import Any

import pytest
from django.test import Client

from apps.catalog.tests.helpers import make_brand, make_category, make_product_model
from apps.listings import services
from apps.listings.tests.helpers import (
    give_photo,
    make_admin,
    make_listing,
    make_live_listing,
    ready_piece,
)
from apps.pieces.models import Piece

pytestmark = pytest.mark.django_db

LISTINGS = "/api/v1/listings/"


def results(response: Any) -> list[dict[str, Any]]:
    assert response.status_code == 200, response.content
    body = response.json()
    assert set(body) == {"next", "previous", "results"}
    return list(body["results"])


def ids(response: Any) -> list[str]:
    return [row["id"] for row in results(response)]


def test_a_live_listing_matches_the_contract(client: Client) -> None:
    design = make_product_model("Kelly 28")
    piece = ready_piece(
        product_model=design,
        condition_grade="excellent",
        serial_or_date_code="X-SECRET-42",
        description="Gold Togo leather, gold hardware.",
        size_label="28",
    )
    listing = make_live_listing(piece, ask_minor=1_250_000)

    [row] = results(client.get(LISTINGS))

    assert row["id"] == str(listing.pk)
    assert row["status"] == "live"
    assert row["fulfilment"] == "from_vault"
    assert row["ask"] == {"amount": 1_250_000, "currency": "USD"}
    assert row["reservable"] is False
    assert row["reserved_until"] is None
    assert row["verification_label"] == "verification_pending"
    assert row["published_at"]
    assert "floor" not in row  # the seller's minimum is never public
    shown = row["piece"]
    assert shown["title"] == "Kelly 28, Gold Togo"
    assert shown["brand"]["slug"] == "hermes"
    assert shown["category"]["slug"] == "bags"
    assert shown["product_model"]["slug"] == "kelly-28"
    assert shown["condition_grade"] == "excellent"
    assert shown["size_label"] == "28"
    assert "X-SECRET-42" not in str(row)
    assert "serial_or_date_code" not in shown
    [photo] = shown["media"]
    assert photo["kind"] == "listing"
    assert photo["url"].startswith("http://testserver/media/pieces/")
    assert photo["alt"] == "Kelly 28, Gold Togo, listing photo 1"


def test_browsing_needs_no_login_and_sets_no_cookie(client: Client) -> None:
    make_live_listing()

    response = client.get(LISTINGS)

    assert response.status_code == 200
    assert "sessionid" not in response.cookies
    assert "csrftoken" not in response.cookies


def test_only_live_listings_are_shown(client: Client) -> None:
    admin = make_admin()
    live = make_live_listing()
    make_listing()  # a draft
    withdrawn = make_live_listing()
    services.withdraw_listing(withdrawn, by=admin)

    assert ids(client.get(LISTINGS)) == [str(live.pk)]


def test_a_piece_found_not_authentic_disappears_from_browse(client: Client) -> None:
    listing = make_live_listing()
    Piece.objects.filter(pk=listing.piece_id).update(verification_status="not_authentic")

    assert ids(client.get(LISTINGS)) == []
    assert client.get(f"{LISTINGS}{listing.pk}/").status_code == 404


def test_newest_first_and_paged_with_a_cursor(client: Client) -> None:
    made = [str(make_live_listing().pk) for _ in range(3)]

    first = client.get(LISTINGS, {"page_size": 2}).json()
    second = client.get(LISTINGS, {"page_size": 2, "cursor": first["next"]}).json()

    seen = [row["id"] for row in first["results"] + second["results"]]
    assert seen == list(reversed(made))
    assert second["next"] is None


def test_filter_by_brand_and_category_slugs(client: Client) -> None:
    chanel, bags, jewellery = (
        make_brand("Chanel"),
        make_category("Bags"),
        make_category("Jewellery"),
    )
    bracelets = make_category("Bracelets", parent=jewellery)
    hermes_bag = make_live_listing(ready_piece(category=bags))
    chanel_bag = make_live_listing(ready_piece(brand=chanel, category=bags))
    bracelet = make_live_listing(ready_piece(category=bracelets))

    assert ids(client.get(LISTINGS, {"brand": "chanel"})) == [str(chanel_bag.pk)]
    assert set(ids(client.get(LISTINGS, {"category": "bags"}))) == {
        str(hermes_bag.pk),
        str(chanel_bag.pk),
    }
    # A parent category also shows the pieces in the categories under it.
    assert ids(client.get(LISTINGS, {"category": "jewellery"})) == [str(bracelet.pk)]
    assert ids(client.get(LISTINGS, {"brand": "no-such-brand"})) == []


def test_filter_by_lowest_condition(client: Client) -> None:
    excellent = make_live_listing(ready_piece(condition_grade="excellent"))
    good = make_live_listing(ready_piece(condition_grade="good"))
    make_live_listing(ready_piece(condition_grade=""))  # not graded yet

    assert ids(client.get(LISTINGS, {"condition_min": "very_good"})) == [str(excellent.pk)]
    assert set(ids(client.get(LISTINGS, {"condition_min": "good"}))) == {
        str(excellent.pk),
        str(good.pk),
    }


def test_filter_by_highest_price_in_cents(client: Client) -> None:
    cheap = make_live_listing(ask_minor=500_00)
    make_live_listing(ask_minor=900_00)

    assert ids(client.get(LISTINGS, {"price_max": 500_00})) == [str(cheap.pk)]


def test_search_matches_title_brand_and_design_words(client: Client) -> None:
    chanel = make_brand("Chanel")
    flap = make_live_listing(
        ready_piece(
            brand=chanel, title="Classic Flap, black caviar", category=make_category("Flap bags")
        )
    )
    kelly = make_live_listing(
        ready_piece(product_model=make_product_model("Kelly 28"), title="Gold Togo")
    )

    assert ids(client.get(LISTINGS, {"q": "chanel black"})) == [str(flap.pk)]
    assert ids(client.get(LISTINGS, {"q": "KELLY"})) == [str(kelly.pk)]
    assert ids(client.get(LISTINGS, {"q": "chanel kelly"})) == []


@pytest.mark.parametrize(
    "params",
    [
        {"condition_min": "mint"},
        {"price_max": "-1"},
        {"price_max": "ten"},
        {"brand": "not a slug!"},
    ],
)
def test_bad_filters_are_a_400_with_the_field(client: Client, params: dict[str, str]) -> None:
    response = client.get(LISTINGS, params)

    assert response.status_code == 400
    assert response["Content-Type"] == "application/problem+json"
    assert [error["field"] for error in response.json()["errors"]] == list(params)


def test_one_listing_by_id(client: Client) -> None:
    listing = make_live_listing()

    response = client.get(f"{LISTINGS}{listing.pk}/")

    assert response.status_code == 200
    assert response.json()["id"] == str(listing.pk)


def test_a_draft_or_unknown_listing_is_not_found(client: Client) -> None:
    draft = make_listing()

    for path in (f"{LISTINGS}{draft.pk}/", f"{LISTINGS}01a20786-8c65-76ee-b6de-bcf8976153ad/"):
        response = client.get(path)
        assert response.status_code == 404
        assert response.json()["code"] == "not_found"


@pytest.mark.parametrize(
    ("basis", "status", "label"),
    [
        ("samwab_checked", "verified", "verified"),
        ("samwab_checked", "unverified", "verification_pending"),
        ("buyer_authenticated", "unverified", "buyer_authenticates"),
    ],
)
def test_the_verification_label(client: Client, basis: str, status: str, label: str) -> None:
    piece = ready_piece(authentication_basis=basis)
    Piece.objects.filter(pk=piece.pk).update(verification_status=status)
    listing = make_live_listing(piece)

    assert client.get(f"{LISTINGS}{listing.pk}/").json()["verification_label"] == label


def test_photos_come_in_their_order(client: Client) -> None:
    piece = ready_piece()
    give_photo(piece, kind="flaw")
    listing = make_live_listing(piece)

    media = client.get(f"{LISTINGS}{listing.pk}/").json()["piece"]["media"]

    assert [photo["kind"] for photo in media] == ["listing", "flaw"]
    assert [photo["sort_order"] for photo in media] == [1, 2]


def test_browsing_runs_a_fixed_number_of_queries(
    client: Client, django_assert_max_num_queries: Any
) -> None:
    for _ in range(5):
        make_live_listing()

    with django_assert_max_num_queries(3):
        results(client.get(LISTINGS))


def test_creating_a_listing_through_the_api_is_not_open_yet(client: Client) -> None:
    assert client.post(LISTINGS, {}, content_type="application/json").status_code == 405
