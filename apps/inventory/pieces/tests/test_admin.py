"""Tests for the piece screens in the admin site."""

from typing import Any

import pytest
from django.test import Client

from apps.inventory.catalog.tests.helpers import make_material, make_product_model
from apps.inventory.pieces.models import Piece
from apps.inventory.pieces.tests.helpers import make_house, make_piece
from apps.users.accounts.models import User

pytestmark = pytest.mark.django_db

ADMIN = "/admin/pieces/piece"


@pytest.fixture
def boss_client(client: Client) -> Client:
    client.force_login(User.objects.create_superuser("boss@samwab.com", "correct-horse-9"))
    return client


def page(response: Any) -> str:
    assert response.status_code == 200, response.status_code
    return str(response.content.decode())


def form(**fields: str) -> dict[str, str]:
    kelly = make_product_model("Kelly 28", department="women")
    togo = make_material("Togo leather")
    values = {
        "product_model": str(kelly.id),
        "brand": str(kelly.brand_id),
        "category": str(kelly.category_id),
        "title": "Kelly 28, Gold Togo",
        "description": "",
        "department": "",
        "size_system": "",
        "size_label": "",
        "production_year": "2019",
        "attributes": "{}",
        "hs_code": "",
        "serial_or_date_code": "D",
        "source": "house_stock",
        "home_country": "US",
        "authentication_basis": "",
        "acquisition_cost_minor": "900000",
        "condition_grade": "excellent",
        "current_owner": str(make_house().id),
        "photos-TOTAL_FORMS": "0",  # the photos section, empty
        "photos-INITIAL_FORMS": "0",
        "piecematerial_set-TOTAL_FORMS": "1",
        "piecematerial_set-INITIAL_FORMS": "0",
        "piecematerial_set-0-material": str(togo.id),
    }
    values.update(fields)
    return values


def test_list_add_and_change_screens_open(boss_client: Client) -> None:
    piece = make_piece(title="Kelly 28, Gold Togo")

    assert "Kelly 28, Gold Togo" in page(boss_client.get(f"{ADMIN}/", {"q": "kelly"}))
    page(boss_client.get(f"{ADMIN}/add/"))
    page(boss_client.get(f"{ADMIN}/{piece.id}/change/"))


def test_staff_register_a_piece(boss_client: Client) -> None:
    response = boss_client.post(f"{ADMIN}/add/", form())

    assert response.status_code == 302, page(response)
    piece = Piece.objects.get()
    assert piece.department == "women"  # taken from the design
    assert [material.name for material in piece.materials.all()] == ["Togo leather"]
    assert piece.serial_or_date_code == "D"


def test_the_admin_shows_why_a_piece_is_refused(boss_client: Client) -> None:
    response = boss_client.post(f"{ADMIN}/add/", form(home_country="ng"))

    assert "Use the two-letter country code" in page(response)
    assert not Piece.objects.exists()


def test_statuses_are_shown_but_cannot_be_edited(boss_client: Client) -> None:
    piece = make_piece()

    html = page(boss_client.get(f"{ADMIN}/{piece.id}/change/"))

    assert "Unverified" in html
    assert 'name="verification_status"' not in html
    assert 'name="custody_status"' not in html


def test_pieces_are_never_deleted(boss_client: Client) -> None:
    piece = make_piece()

    assert boss_client.get(f"{ADMIN}/{piece.id}/delete/").status_code == 403
    assert Piece.objects.filter(pk=piece.pk).exists()


def test_staff_fix_a_piece_and_its_statuses_stay(boss_client: Client) -> None:
    values = form()
    assert boss_client.post(f"{ADMIN}/add/", values).status_code == 302
    piece = Piece.objects.get()
    Piece.objects.filter(pk=piece.pk).update(custody_status="in_transit")
    values.update(
        {
            "title": "Kelly 28, Gold Togo, 2019",
            "piecematerial_set-TOTAL_FORMS": "0",
            "piecematerial_set-INITIAL_FORMS": "0",
        }
    )

    response = boss_client.post(f"{ADMIN}/{piece.id}/change/", values)

    assert response.status_code == 302, page(response)
    piece.refresh_from_db()
    assert piece.title == "Kelly 28, Gold Togo, 2019"
    assert piece.custody_status == "in_transit"
    assert piece.materials.count() == 1
