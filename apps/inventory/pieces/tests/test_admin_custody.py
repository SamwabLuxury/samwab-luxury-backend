"""E7a: staff move a piece into the vault from the piece list, with no shell.

Three actions follow the custody path (with the owner -> in transit -> at intake ->
in the vault) through ``services.move_custody``, so each step is checked by the
state machine and recorded in the audit log. Until the custody build (16) adds
custody events, this is how a piece becomes ready to list on the live site.
"""

from typing import Any

import pytest
from django.contrib.auth.models import Permission
from django.test import Client

from apps.inventory.pieces.models import Piece
from apps.inventory.pieces.tests.helpers import make_piece
from apps.platform.audit.models import AuditEvent
from apps.shop.listings.models import Listing
from apps.shop.listings.tests.helpers import give_photo, make_admin
from apps.users.accounts.models import User
from apps.users.accounts.tests.helpers import PASSWORD, admin_login, make_staff

pytestmark = pytest.mark.django_db

LIST = "/admin/pieces/piece/"


def act(client: Client, action: str, *pieces: Piece) -> Any:
    return client.post(
        LIST, {"action": action, "_selected_action": [str(p.pk) for p in pieces]}, follow=True
    )


def custody(piece: Piece) -> str:
    piece.refresh_from_db()
    return piece.custody_status


@pytest.fixture
def clerk_client(client: Client) -> Client:
    admin_login(client, make_staff("intake@samwab.com", "intake_staff"))
    return client


def test_a_piece_walks_into_the_vault_in_three_steps(clerk_client: Client) -> None:
    piece = make_piece()

    page = act(clerk_client, "mark_in_transit", piece).content.decode()
    assert custody(piece) == "in_transit"
    assert "on its way to the vault" in page

    page = act(clerk_client, "mark_received", piece).content.decode()
    assert custody(piece) == "at_intake"
    assert "received at intake" in page

    page = act(clerk_client, "put_in_vault", piece).content.decode()
    assert custody(piece) == "in_vault"
    assert "is in the vault" in page

    moves = AuditEvent.objects.filter(action="pieces.piece.custody_moved").order_by("id")
    assert [e.changes["custody_status"] for e in moves] == [
        {"from": "with_owner", "to": "in_transit"},
        {"from": "in_transit", "to": "at_intake"},
        {"from": "at_intake", "to": "in_vault"},
    ]
    assert {e.actor.email for e in moves if e.actor} == {"intake@samwab.com"}


def test_a_step_out_of_order_is_refused_with_a_plain_message(clerk_client: Client) -> None:
    piece = make_piece()

    page = act(clerk_client, "put_in_vault", piece).content.decode()

    assert custody(piece) == "with_owner"
    assert "Kelly 28, Gold Togo: it is with its owner" in page
    assert "Received at intake" in page  # the message names the step it needs first
    assert not AuditEvent.objects.filter(action="pieces.piece.custody_moved").exists()


def test_a_piece_in_the_vault_cannot_be_marked_in_transit_here(clerk_client: Client) -> None:
    """Leaving the vault means a sale handed to a courier: the order flow does that."""
    piece = make_piece(custody_status="in_vault")

    page = act(clerk_client, "mark_in_transit", piece).content.decode()

    assert custody(piece) == "in_vault"
    assert "only a piece still with its owner" in page


def test_several_pieces_at_once_each_get_their_own_answer(clerk_client: Client) -> None:
    ready = make_piece(title="Birkin 30", custody_status="at_intake")
    early = make_piece(title="Speedy 25", brand=ready.brand, category=ready.category)

    page = act(clerk_client, "put_in_vault", ready, early).content.decode()

    assert custody(ready) == "in_vault"
    assert custody(early) == "with_owner"
    assert "Birkin 30 is in the vault" in page
    assert "Speedy 25: it is with its owner" in page


def test_staff_without_the_change_right_do_not_see_the_actions(client: Client) -> None:
    viewer = make_staff("viewer@samwab.com")
    viewer.user_permissions.add(*Permission.objects.filter(codename="view_piece"))
    admin_login(client, viewer)
    piece = make_piece()

    page = client.get(LIST).content.decode()
    assert "put_in_vault" not in page

    act(client, "put_in_vault", piece)
    assert custody(piece) == "with_owner"


def test_people_who_are_not_staff_cannot_reach_the_actions(client: Client) -> None:
    client.force_login(User.objects.create_user("ada@example.com", PASSWORD))
    piece = make_piece(custody_status="at_intake")

    response = client.post(LIST, {"action": "put_in_vault", "_selected_action": [str(piece.pk)]})

    assert response.status_code == 302
    assert custody(piece) == "at_intake"


def test_the_actions_cannot_delete_pieces(clerk_client: Client) -> None:
    make_piece()  # the admin shows its actions only above a list with rows

    page = clerk_client.get(LIST).content.decode()

    assert "delete_selected" not in page
    for action in ("mark_in_transit", "mark_received", "put_in_vault"):
        assert action in page


# ---------- the whole way to a live listing, with admin screens only ----------


def test_from_a_new_piece_to_a_live_listing_without_a_shell(client: Client) -> None:
    admin_login(client, make_admin())
    piece = make_piece()
    give_photo(piece)

    for action in ("mark_in_transit", "mark_received", "put_in_vault"):
        act(client, action, piece)
    client.post(
        "/admin/listings/listing/add/",
        {
            "piece": str(piece.pk),
            "fulfilment": "from_vault",
            "ask_minor": "1250000",
            "price_changes-TOTAL_FORMS": "0",
            "price_changes-INITIAL_FORMS": "0",
        },
    )
    listing = Listing.objects.get(piece=piece)
    client.post(
        "/admin/listings/listing/",
        {"action": "publish_selected", "_selected_action": [str(listing.pk)]},
    )

    listing.refresh_from_db()
    assert listing.status == "live"
    assert client.get(f"/api/v1/listings/{listing.pk}/").status_code == 200
