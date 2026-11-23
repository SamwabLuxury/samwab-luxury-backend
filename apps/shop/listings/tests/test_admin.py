"""Staff list house stock in the admin site: draft, publish, change the price, withdraw."""

from typing import Any

import pytest
from django.test import Client

from apps.inventory.pieces.tests.helpers import make_piece
from apps.platform.audit.models import AuditEvent
from apps.shop.listings.models import Listing
from apps.shop.listings.tests.helpers import (
    make_admin,
    make_listing,
    make_live_listing,
    ready_piece,
)
from apps.users.accounts.tests.helpers import make_staff

pytestmark = pytest.mark.django_db

ADD = "/admin/listings/listing/add/"
LIST = "/admin/listings/listing/"


@pytest.fixture
def admin_client(client: Client) -> Client:
    client.force_login(make_admin())
    return client


def change_url(listing: Listing) -> str:
    return f"{LIST}{listing.pk}/change/"


def form(**fields: str) -> dict[str, str]:
    """The listing form as the browser sends it, with the empty price history section."""
    return {"price_changes-TOTAL_FORMS": "0", "price_changes-INITIAL_FORMS": "0", **fields}


def act(client: Client, action: str, *listings: Listing) -> Any:
    return client.post(
        LIST, {"action": action, "_selected_action": [str(x.pk) for x in listings]}, follow=True
    )


def test_staff_draft_a_listing_for_a_piece(admin_client: Client) -> None:
    piece = ready_piece()

    response = admin_client.post(
        ADD, form(piece=str(piece.pk), fulfilment="from_vault", ask_minor="1250000")
    )

    assert response.status_code == 302, response.content.decode()[:3000]
    listing = Listing.objects.get()
    assert (listing.status, listing.seller, listing.ask_minor) == (
        "draft",
        piece.current_owner,
        1_250_000,
    )
    assert AuditEvent.objects.filter(action="listings.listing.created").exists()


def test_the_form_shows_the_rule_that_failed(admin_client: Client) -> None:
    piece = make_piece(source="consigned")

    response = admin_client.post(
        ADD, {"piece": str(piece.pk), "fulfilment": "from_vault", "ask_minor": "100"}
    )

    assert response.status_code == 200
    assert "Consigned pieces are listed by their owners" in response.content.decode()
    assert not Listing.objects.exists()


def test_a_second_open_listing_is_refused_on_the_form(admin_client: Client) -> None:
    listing = make_listing()

    response = admin_client.post(
        ADD, {"piece": str(listing.piece_id), "fulfilment": "from_vault", "ask_minor": "100"}
    )

    assert response.status_code == 200
    assert "already has an open listing" in response.content.decode()


def test_publish_and_withdraw_with_actions(admin_client: Client) -> None:
    listing = make_listing()

    page = act(admin_client, "publish_selected", listing).content.decode()
    listing.refresh_from_db()
    assert listing.status == "live"
    assert "Published" in page

    act(admin_client, "withdraw_selected", listing)
    listing.refresh_from_db()
    assert listing.status == "withdrawn"


def test_a_listing_that_is_not_ready_shows_why(admin_client: Client) -> None:
    listing = make_listing(make_piece())  # no photo, not in the vault

    page = act(admin_client, "publish_selected", listing).content.decode()

    listing.refresh_from_db()
    assert listing.status == "draft"
    assert "Add at least one listing photo" in page


def test_changing_the_price_is_recorded(admin_client: Client) -> None:
    listing = make_live_listing(ask_minor=1_000_00)

    response = admin_client.post(change_url(listing), form(ask_minor="90000"))

    assert response.status_code == 302, response.content.decode()[:3000]
    listing.refresh_from_db()
    assert listing.ask_minor == 900_00
    assert listing.price_changes.get().old_ask_minor == 1_000_00
    page = admin_client.get(change_url(listing)).content.decode()
    assert "1000.00 USD" in page and "900.00 USD" in page  # the price history on the page


def test_a_withdrawn_listing_cannot_be_edited_or_deleted(admin_client: Client) -> None:
    listing = make_listing()
    act(admin_client, "withdraw_selected", listing)

    page = admin_client.get(change_url(listing)).content.decode()

    assert 'name="ask_minor"' not in page
    assert admin_client.post(f"{LIST}{listing.pk}/delete/").status_code == 403


def test_the_piece_and_status_never_change_on_the_form(admin_client: Client) -> None:
    listing = make_listing()
    other = ready_piece(title="Birkin 30")

    admin_client.post(
        change_url(listing),
        {"piece": str(other.pk), "status": "live", "fulfilment": "from_vault", "ask_minor": "100"},
    )

    listing.refresh_from_db()
    assert (listing.piece_id, listing.status) != (other.pk, "live")
    assert listing.piece_id != other.pk
    assert listing.status == "draft"


def test_staff_without_a_listing_role_cannot_see_listings(client: Client) -> None:
    client.force_login(make_staff("intake@samwab.com", "intake_staff"))

    assert client.get(LIST).status_code == 403
