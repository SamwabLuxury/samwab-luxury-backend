"""Small helpers that make listings for tests."""

from typing import Any

from apps.accounts.models import User
from apps.catalog.models import Brand, Category
from apps.catalog.tests.helpers import make_brand, make_category
from apps.listings import services
from apps.listings.models import Listing
from apps.pieces.models import Media, Piece
from apps.pieces.tests.helpers import make_piece


def make_admin(email: str = "admin@samwab.com") -> User:
    """An admin (superuser); the same one each time it is asked for."""
    found = User.objects.filter(email=email).first()
    return found or User.objects.create_superuser(email, "correct-horse-9")


def put_in_vault(piece: Piece) -> Piece:
    """Skip the custody path (tested in the pieces app): the piece is on a vault shelf."""
    Piece.objects.filter(pk=piece.pk).update(custody_status="in_vault")
    piece.refresh_from_db()
    return piece


def give_photo(piece: Piece, kind: str = "listing") -> Media:
    """A photo row without a real file: enough for the listing rules."""
    order = piece.photos.count() + 1
    return Media.objects.create(
        piece=piece,
        kind=kind,
        file=f"pieces/{piece.pk}/photo-{order}.jpg",
        sha256="a" * 64,
        width=800,
        height=600,
        sort_order=order,
    )


def ready_piece(**fields: Any) -> Piece:
    """House stock in the vault with a listing photo: ready to be listed.

    Pieces share one brand (Hermès) and one category (Bags) unless a test names others.
    """
    if "product_model" not in fields:
        if "brand" not in fields:
            fields["brand"] = Brand.objects.filter(slug="hermes").first() or make_brand()
        if "category" not in fields:
            fields["category"] = Category.objects.filter(slug="bags").first() or make_category()
    piece = put_in_vault(make_piece(**fields))
    give_photo(piece)
    return piece


def make_listing(piece: Piece | None = None, *, by: User | None = None, **fields: Any) -> Listing:
    """A draft listing for a ready piece, saved through the service."""
    fields.setdefault("fulfilment", "from_vault")
    fields.setdefault("ask_minor", 1_250_000)
    listing = Listing(piece=piece or ready_piece(), **fields)
    return services.create_listing(listing, by=by or make_admin())


def make_live_listing(piece: Piece | None = None, **fields: Any) -> Listing:
    admin = make_admin()
    listing = make_listing(piece, by=admin, **fields)
    return services.publish_listing(listing, by=admin)
