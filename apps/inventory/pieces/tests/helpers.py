"""Small helpers that make pieces for tests."""

from typing import Any

from apps.inventory.catalog.tests.helpers import make_brand, make_category
from apps.inventory.pieces.models import Piece
from apps.users.accounts.models import User


def make_house() -> User:
    """Samwab's own account, which owns house stock."""
    found = User.objects.filter(is_house_account=True).first()
    return found or User.objects.create_user("house@samwab.com", None, is_house_account=True)


def make_owner(email: str = "owner@example.com") -> User:
    return User.objects.create_user(email, "correct-horse-9")


def make_piece(**fields: Any) -> Piece:
    design = fields.get("product_model")
    if "brand" not in fields:
        fields["brand"] = design.brand if design else make_brand()
    if "category" not in fields:
        fields["category"] = design.category if design else make_category()
    fields.setdefault("title", "Kelly 28, Gold Togo")
    fields.setdefault("department", "women")
    fields.setdefault("source", "house_stock")
    fields.setdefault("home_country", "US")
    if "current_owner" not in fields:
        fields["current_owner"] = (
            make_house() if fields["source"] == "house_stock" else make_owner()
        )
    return Piece.objects.create(**fields)
