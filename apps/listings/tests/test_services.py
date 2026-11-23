"""Writes to listings: create, change the price, publish, withdraw. Each is audited."""

import pytest
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.core.exceptions import ConflictError
from apps.core.state_machine import IllegalTransitionError
from apps.listings import services
from apps.listings.exceptions import ListingNotReadyError
from apps.listings.models import Listing
from apps.listings.tests.helpers import (
    give_photo,
    make_admin,
    make_listing,
    make_live_listing,
    put_in_vault,
)
from apps.pieces.models import Piece
from apps.pieces.tests.helpers import make_piece

pytestmark = pytest.mark.django_db


def actions() -> list[str]:
    return list(AuditEvent.objects.order_by("id").values_list("action", flat=True))


def test_creating_a_listing_is_audited() -> None:
    listing = make_listing()

    assert "listings.listing.created" in actions()
    assert AuditEvent.objects.get(action="listings.listing.created").object_id == listing.pk


def test_a_second_open_listing_for_a_piece_is_refused_as_a_conflict() -> None:
    listing = make_listing()

    with pytest.raises(ConflictError) as refused:
        make_listing(listing.piece)

    assert refused.value.code == "piece_already_listed"


def test_publishing_puts_the_listing_live_with_a_time() -> None:
    before = timezone.now()

    listing = make_live_listing()

    listing.refresh_from_db()
    assert listing.status == "live"
    assert listing.published_at is not None and listing.published_at >= before
    assert "listings.listing.published" in actions()


@pytest.mark.parametrize(
    ("prepare", "reason"),
    [
        ("no_photo", "Add at least one listing photo"),
        ("not_in_vault", "is not in the vault"),
        ("not_authentic", "not authentic"),
    ],
)
def test_a_listing_that_is_not_ready_cannot_be_published(prepare: str, reason: str) -> None:
    piece = put_in_vault(make_piece())
    if prepare != "no_photo":
        give_photo(piece)
    if prepare == "not_in_vault":
        Piece.objects.filter(pk=piece.pk).update(custody_status="at_intake")
    if prepare == "not_authentic":
        Piece.objects.filter(pk=piece.pk).update(verification_status="not_authentic")
    admin = make_admin()
    listing = make_listing(piece, by=admin)

    with pytest.raises(ListingNotReadyError) as refused:
        services.publish_listing(listing, by=admin)

    assert reason in refused.value.message
    assert refused.value.status_code == 422
    listing.refresh_from_db()
    assert listing.status == "draft"


def test_a_condition_photo_alone_is_not_enough_to_publish() -> None:
    piece = put_in_vault(make_piece())
    give_photo(piece, kind="condition")
    admin = make_admin()

    with pytest.raises(ListingNotReadyError):
        services.publish_listing(make_listing(piece, by=admin), by=admin)


def test_a_piece_shipped_from_home_need_not_be_in_the_vault() -> None:
    piece = make_piece()
    give_photo(piece)

    listing = make_live_listing(piece, fulfilment="from_home")

    assert listing.status == "live"


def test_withdrawing_takes_a_listing_off_sale() -> None:
    admin = make_admin()
    listing = make_live_listing()

    services.withdraw_listing(listing, by=admin)

    listing.refresh_from_db()
    assert listing.status == "withdrawn"
    assert "listings.listing.withdrawn" in actions()


def test_a_withdrawn_listing_cannot_be_published_again() -> None:
    admin = make_admin()
    listing = make_listing(by=admin)
    services.withdraw_listing(listing, by=admin)

    with pytest.raises(IllegalTransitionError):
        services.publish_listing(listing, by=admin)


def test_publishing_reads_the_status_from_the_database() -> None:
    admin = make_admin()
    listing = make_listing(by=admin)
    Listing.objects.filter(pk=listing.pk).update(status="withdrawn")  # someone else, meanwhile

    with pytest.raises(IllegalTransitionError):
        services.publish_listing(listing, by=admin)


def test_changing_the_price_records_the_old_and_new_ask() -> None:
    admin = make_admin()
    listing = make_live_listing(ask_minor=1_000_00)

    services.change_ask(listing, ask_minor=900_00, by=admin)

    listing.refresh_from_db()
    assert listing.ask_minor == 900_00
    change = listing.price_changes.get()
    assert (change.old_ask_minor, change.new_ask_minor, change.changed_by) == (
        1_000_00,
        900_00,
        admin,
    )
    assert "listings.listing.changed" in actions()


def test_the_same_price_records_nothing() -> None:
    admin = make_admin()
    listing = make_listing(ask_minor=500_00, by=admin)
    count = AuditEvent.objects.count()

    services.change_ask(listing, ask_minor=500_00, by=admin)

    assert not listing.price_changes.exists()
    assert AuditEvent.objects.count() == count


def test_a_closed_listing_keeps_its_price() -> None:
    admin = make_admin()
    listing = make_listing(by=admin)
    services.withdraw_listing(listing, by=admin)

    with pytest.raises(ConflictError) as refused:
        services.change_ask(listing, ask_minor=1, by=admin)

    assert refused.value.code == "listing_closed"


def test_a_price_of_zero_is_refused() -> None:
    admin = make_admin()
    listing = make_listing(by=admin)

    with pytest.raises(Exception, match="ask_minor"):
        services.change_ask(listing, ask_minor=0, by=admin)
