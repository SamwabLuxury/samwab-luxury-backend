"""Every staff change to a piece leaves one audit event, written with the change."""

import pytest
from django.test import Client

from apps.inventory.catalog.tests.helpers import make_material
from apps.inventory.pieces import services
from apps.inventory.pieces.models import Piece
from apps.inventory.pieces.tests.helpers import make_house, make_piece
from apps.inventory.pieces.tests.test_admin import form
from apps.platform.audit.models import AuditEvent
from apps.platform.core.exceptions import ConflictError
from apps.users.accounts.models import User
from apps.users.accounts.tests.helpers import make_staff

pytestmark = pytest.mark.django_db

ADMIN = "/admin/pieces/piece"


@pytest.fixture
def clerk() -> User:
    user: User = make_staff("intake@samwab.com", "intake_staff")
    return user


def actions() -> list[str]:
    return list(AuditEvent.objects.order_by("id").values_list("action", flat=True))


def test_registering_a_piece_records_its_values(clerk: User) -> None:
    template = make_piece()
    piece = Piece(
        brand=template.brand,
        category=template.category,
        title="Birkin 30",
        department="women",
        source="house_stock",
        home_country="US",
        current_owner=make_house(),
    )

    services.register_piece(piece, by=clerk)

    event = AuditEvent.objects.get()
    assert (event.action, event.object_id, event.actor) == ("pieces.piece.created", piece.id, clerk)
    assert event.changes["title"] == {"to": "Birkin 30"}
    assert event.changes["custody_status"] == {"to": "with_owner"}


def test_updating_a_piece_records_only_what_changed(clerk: User) -> None:
    piece = make_piece(title="Kelly 28")
    piece.title = "Kelly 28, Gold Togo"

    services.update_piece(piece, by=clerk)

    assert AuditEvent.objects.get().changes == {
        "title": {"from": "Kelly 28", "to": "Kelly 28, Gold Togo"}
    }


def test_a_custody_move_is_recorded(clerk: User) -> None:
    piece = make_piece(custody_status="at_intake")

    services.move_custody(piece, to="in_vault", by=clerk)

    event = AuditEvent.objects.get()
    assert event.action == "pieces.piece.custody_moved"
    assert event.changes == {"custody_status": {"from": "at_intake", "to": "in_vault"}}


def test_a_verification_result_is_recorded(clerk: User) -> None:
    piece = make_piece()

    services.set_verification(piece, to="verified", by=clerk)

    event = AuditEvent.objects.get()
    assert event.action == "pieces.piece.verification_set"
    assert event.changes == {"verification_status": {"from": "unverified", "to": "verified"}}


def test_a_refused_move_records_nothing(clerk: User) -> None:
    piece = make_piece()

    with pytest.raises(ConflictError):
        services.move_custody(piece, to="in_vault", by=clerk)

    assert not AuditEvent.objects.exists()


def test_registering_in_the_admin_records_the_piece_and_its_materials(
    client: Client, clerk: User
) -> None:
    client.force_login(clerk)

    response = client.post(f"{ADMIN}/add/", form())

    assert response.status_code == 302
    assert actions() == ["pieces.piece.created", "pieces.piece.materials_changed"]
    materials = AuditEvent.objects.get(action="pieces.piece.materials_changed")
    assert materials.object_id == Piece.objects.get().id
    assert materials.changes == {"materials": {"from": [], "to": ["Togo leather"]}}


def test_changing_the_materials_in_the_admin_is_recorded(client: Client, clerk: User) -> None:
    client.force_login(clerk)
    values = form()
    client.post(f"{ADMIN}/add/", values)
    piece = Piece.objects.get()
    link = piece.piecematerial_set.get()
    gold = make_material("Gold-plated hardware")
    values.update(
        {
            "piecematerial_set-TOTAL_FORMS": "2",
            "piecematerial_set-INITIAL_FORMS": "1",
            "piecematerial_set-0-id": str(link.id),
            "piecematerial_set-0-piece": str(piece.id),
            "piecematerial_set-0-material": str(link.material_id),
            "piecematerial_set-1-material": str(gold.id),
        }
    )

    response = client.post(f"{ADMIN}/{piece.id}/change/", values)

    assert response.status_code == 302, response.content.decode()[:2000]
    last = AuditEvent.objects.order_by("-id").first()
    assert last is not None
    assert last.action == "pieces.piece.materials_changed"
    assert last.changes == {
        "materials": {"from": ["Togo leather"], "to": ["Gold-plated hardware", "Togo leather"]}
    }
