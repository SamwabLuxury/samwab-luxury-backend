"""The public passport page: ``GET /api/v1/passports/{public_code}/`` (in the contract).

No login. It shows the piece, who owns it (first name and initial only), its condition
reports and restorations. Ownership history and certificates come with builds 17 and 29.
"""

from typing import Any

import pytest
from django.test import Client

from apps.inventory.passports import services
from apps.inventory.passports.tests.helpers import a_piece, checker, verified
from apps.inventory.pieces.tests.helpers import make_owner
from apps.shop.listings.tests.helpers import make_live_listing, ready_piece

pytestmark = pytest.mark.django_db

PASSPORTS = "/api/v1/passports/"


def get(client: Client, code: str) -> Any:
    return client.get(f"{PASSPORTS}{code}/")


def test_a_passport_answers_without_login(client: Client) -> None:
    piece = a_piece(title="Kelly 28, Gold Togo", condition_grade="excellent")
    passport = verified(piece)

    response = get(client, passport.public_code)

    assert response.status_code == 200
    body = response.json()
    assert body["passport_number"] == 1
    assert body["printed_number"] == "0000 01"
    assert body["public_code"] == passport.public_code
    assert body["piece"]["title"] == "Kelly 28, Gold Togo"
    assert body["piece"]["verification_status"] == "verified"
    assert body["owner_display"] == "Samwab"  # house stock
    assert body["ownership_history"] == []
    assert body["certificates"] == []
    assert body["issued_at"]


def test_the_code_works_in_lower_case(client: Client) -> None:
    passport = verified(a_piece())

    assert get(client, passport.public_code.lower()).status_code == 200


def test_condition_reports_and_restorations_newest_first(client: Client) -> None:
    piece = a_piece()
    passport = verified(piece)
    flaw = {"type": "corner_rub", "severity": "minor", "where": "Base", "note": "Light."}
    services.add_condition_report(
        piece, grade="excellent", summary="First.", flaws=[], by=checker()
    )
    services.add_condition_report(
        piece, grade="very_good", summary="Later.", flaws=[flaw], by=checker()
    )
    services.add_restoration(
        piece,
        description="Edge paint redone.",
        performed_by="Atelier",
        performed_on=None,
        cost_minor=9_000,
        by=checker(),
    )

    body = get(client, passport.public_code).json()

    reports = body["condition_reports"]
    assert [report["summary"] for report in reports] == ["Later.", "First."]
    assert reports[0]["grade"] == "very_good"
    assert reports[0]["flaws"] == [
        {
            "type": "corner_rub",
            "severity": "minor",
            "where": "Base",
            "note": "Light.",
            "photo": None,
        }
    ]
    assert reports[0]["at"]
    assert body["restorations"] == [
        {"description": "Edge paint redone.", "performed_by": "Atelier", "performed_on": None}
    ]
    assert "cost" not in str(body["restorations"])  # what it cost stays with staff


def test_a_flaw_links_its_photo(client: Client) -> None:
    piece = ready_piece()
    passport = verified(piece)
    photo = piece.photos.get()
    flaw = {"type": "pilling", "severity": "minor", "where": "Handle", "photo_id": str(photo.pk)}
    services.add_condition_report(piece, grade="good", summary="", flaws=[flaw], by=checker())

    shown = get(client, passport.public_code).json()["condition_reports"][0]["flaws"][0]

    assert shown["photo"]["id"] == str(photo.pk)
    assert shown["photo"]["sizes"]["thumb"].startswith("http://testserver/")


@pytest.mark.parametrize(
    ("first", "last", "shown"),
    [("Adaeze", "Obi", "Adaeze O."), ("Adaeze", "", "Adaeze"), ("", "Obi", "Private owner")],
)
def test_an_owner_is_shown_by_first_name_and_initial(
    client: Client, first: str, last: str, shown: str
) -> None:
    owner = make_owner()
    owner.first_name, owner.last_name = first, last
    owner.save()
    passport = verified(a_piece(source="consigned", current_owner=owner))

    assert get(client, passport.public_code).json()["owner_display"] == shown


def test_private_details_never_appear(client: Client) -> None:
    passport = verified(a_piece(serial_or_date_code="SECRET-77", acquisition_cost_minor=500))

    text = get(client, passport.public_code).content.decode()

    assert "SECRET-77" not in text
    assert "acquisition" not in text
    assert "house@samwab.com" not in text


def test_a_hidden_or_unknown_passport_is_not_found(client: Client) -> None:
    passport = verified(a_piece())
    services.set_public(passport, False, by=checker())

    assert get(client, passport.public_code).status_code == 404
    assert get(client, "NOTACODE22").status_code == 404


def test_writing_is_not_allowed(client: Client) -> None:
    passport = verified(a_piece())

    assert client.post(f"{PASSPORTS}{passport.public_code}/").status_code == 405


# ---------- the passport on the shop card and piece page ----------


def test_a_listing_shows_its_passport_number_and_code(client: Client) -> None:
    listing = make_live_listing()
    passport = verified(listing.piece)

    piece = client.get(f"/api/v1/listings/{listing.pk}/").json()["piece"]
    card = client.get("/api/v1/listings/").json()["results"][0]["piece"]

    assert piece["passport_code"] == passport.public_code
    assert piece["passport_number"] == "0000 01"
    assert card["passport_code"] == passport.public_code


def test_a_listing_without_a_passport_says_null(client: Client) -> None:
    listing = make_live_listing()

    piece = client.get(f"/api/v1/listings/{listing.pk}/").json()["piece"]

    assert (piece["passport_code"], piece["passport_number"]) == (None, None)


def test_a_hidden_passport_is_not_shown_on_the_listing(client: Client) -> None:
    listing = make_live_listing()
    services.set_public(verified(listing.piece), False, by=checker())

    piece = client.get(f"/api/v1/listings/{listing.pk}/").json()["piece"]

    assert piece["passport_code"] is None


def test_the_shop_list_costs_no_extra_query_for_passports(
    client: Client, django_assert_max_num_queries: Any
) -> None:
    for _ in range(3):
        verified(make_live_listing().piece)

    with django_assert_max_num_queries(4):  # the shop's existing budget
        client.get("/api/v1/listings/")
