"""The listings table: what the database itself refuses."""

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.core.money import Money
from apps.listings.models import Listing, ListingPriceChange
from apps.listings.tests.helpers import make_listing, ready_piece
from apps.pieces.tests.helpers import make_piece

pytestmark = pytest.mark.django_db


def test_tables_are_named_as_in_the_data_model() -> None:
    assert Listing._meta.db_table == "listings"
    assert ListingPriceChange._meta.db_table == "listing_price_changes"


def test_a_new_listing_is_a_draft_in_dollars() -> None:
    listing = make_listing(ask_minor=99_00)

    assert listing.status == "draft"
    assert listing.currency == "USD"
    assert listing.ask == Money(99_00)
    assert listing.published_at is None


def test_the_seller_is_the_pieces_owner() -> None:
    piece = ready_piece()

    listing = make_listing(piece)

    assert listing.seller_id == piece.current_owner_id


@pytest.mark.parametrize(
    ("field", "value"),
    [("status", "on_sale"), ("fulfilment", "by_post"), ("ask_minor", 0)],
)
def test_the_database_refuses_bad_values(field: str, value: object) -> None:
    listing = make_listing()

    with pytest.raises(IntegrityError), transaction.atomic():
        Listing.objects.filter(pk=listing.pk).update(**{field: value})


def test_a_piece_has_at_most_one_open_listing() -> None:
    listing = make_listing()

    with pytest.raises(IntegrityError), transaction.atomic():
        Listing.objects.create(
            piece=listing.piece,
            seller=listing.seller,
            fulfilment="from_vault",
            ask_minor=10_00,
        )


def test_a_withdrawn_listing_does_not_block_a_new_one() -> None:
    listing = make_listing()
    Listing.objects.filter(pk=listing.pk).update(status="withdrawn")

    again = make_listing(listing.piece)

    assert again.status == "draft"


def test_consigned_pieces_are_not_listed_by_staff_yet() -> None:
    piece = make_piece(source="consigned")

    with pytest.raises(ValidationError) as refused:
        Listing(
            piece=piece, seller=piece.current_owner, fulfilment="from_vault", ask_minor=1
        ).full_clean()

    assert "consigned" in str(refused.value).lower()


def test_house_stock_has_no_floor_price() -> None:
    piece = ready_piece()

    with pytest.raises(ValidationError) as refused:
        Listing(
            piece=piece,
            seller=piece.current_owner,
            fulfilment="from_vault",
            ask_minor=100,
            floor_minor=50,
        ).full_clean()

    assert "floor_minor" in refused.value.message_dict


def test_str_names_the_piece_and_price() -> None:
    listing = make_listing(ask_minor=1_250_000)

    assert str(listing) == "Kelly 28, Gold Togo · 12500.00 USD · draft"
