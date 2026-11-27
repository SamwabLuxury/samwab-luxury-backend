"""Helpers for the passport tests."""

from typing import Any

from apps.inventory.passports import services
from apps.inventory.passports.models import Passport
from apps.inventory.pieces.models import Piece
from apps.users.accounts.models import User
from apps.users.accounts.tests.helpers import make_staff


def checker() -> User:
    """The staff member who checks pieces in these tests."""
    found = User.objects.filter(email="checker@samwab.com").first()
    return found or make_staff("checker@samwab.com")


def verified(piece: Piece) -> Passport:
    """Verify ``piece`` (which issues its passport) and return the passport."""
    return services.verify(piece, by=checker())


def a_piece(**fields: Any) -> Piece:
    """A piece; pieces made this way share one brand and one category."""
    from apps.inventory.catalog.models import Brand, Category
    from apps.inventory.catalog.tests.helpers import make_brand, make_category
    from apps.inventory.pieces.tests.helpers import make_piece

    if "product_model" not in fields:
        fields.setdefault("brand", Brand.objects.first() or make_brand())
        fields.setdefault("category", Category.objects.first() or make_category())
    return make_piece(**fields)
