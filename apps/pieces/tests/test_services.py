"""Tests for piece writes: registering a piece and moving it through its statuses."""

import pytest
from django.core.exceptions import ValidationError

from apps.accounts.models import User
from apps.catalog.tests.helpers import make_category, make_product_model
from apps.core.state_machine import IllegalTransitionError
from apps.pieces import services
from apps.pieces.models import Piece
from apps.pieces.state import CUSTODY, VERIFICATION
from apps.pieces.tests.helpers import make_house, make_piece

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff() -> User:
    return User.objects.create_superuser("staff@samwab.com", "correct-horse-9")


def new_piece(**fields: object) -> Piece:
    """An unsaved piece, as the admin form hands it to the service."""
    kelly = fields.pop("product_model", None) or make_product_model("Kelly 28", department="women")
    values: dict[str, object] = {
        "product_model": kelly,
        "brand": kelly.brand,  # type: ignore[attr-defined]
        "category": kelly.category,  # type: ignore[attr-defined]
        "title": "Kelly 28, Gold Togo",
        "source": "house_stock",
        "home_country": "US",
        "current_owner": make_house(),
        **fields,
    }
    return Piece(**values)


# ---------- registering ----------


def test_register_saves_a_new_piece(staff: User) -> None:
    piece = services.register_piece(new_piece(), by=staff)

    assert Piece.objects.get() == piece
    assert piece.verification_status == "unverified"
    assert piece.custody_status == "with_owner"


def test_register_takes_the_department_from_the_design(staff: User) -> None:
    piece = services.register_piece(new_piece(department=""), by=staff)

    assert piece.department == "women"


def test_a_department_typed_by_staff_wins(staff: User) -> None:
    piece = services.register_piece(new_piece(department="unisex"), by=staff)

    assert piece.department == "unisex"


def test_without_a_department_anywhere_the_piece_is_refused(staff: User) -> None:
    sizeless = make_product_model("Classic", category=make_category("Small leather goods"))

    with pytest.raises(ValidationError) as error:
        services.register_piece(new_piece(product_model=sizeless, department=""), by=staff)

    assert "department" in error.value.message_dict
    assert not Piece.objects.exists()


def test_register_takes_the_hs_code_from_the_category(staff: User) -> None:
    bags = make_category("Bags", default_hs_code="420221")
    kelly = make_product_model("Kelly 28", category=bags, department="women")

    piece = services.register_piece(new_piece(product_model=kelly), by=staff)

    assert piece.hs_code == "420221"


def test_register_checks_every_rule_first(staff: User) -> None:
    with pytest.raises(ValidationError):
        services.register_piece(new_piece(home_country="Nigeria"), by=staff)

    assert not Piece.objects.exists()


def test_update_saves_changes_but_keeps_the_statuses(staff: User) -> None:
    piece = make_piece()
    piece.title = "Kelly 28, Gold Togo, 2019"
    piece.custody_status = "in_vault"  # a form can never move a piece

    services.update_piece(piece, by=staff)

    piece.refresh_from_db()
    assert piece.title == "Kelly 28, Gold Togo, 2019"
    assert piece.custody_status == "with_owner"


# ---------- the two state machines ----------


def test_the_custody_path_from_the_data_model() -> None:
    """with_owner, in_transit, at_intake, in_vault, in_transit, with_buyer."""
    assert CUSTODY.next_states("with_owner") == ["in_transit"]
    assert CUSTODY.next_states("in_transit") == ["at_intake", "with_buyer"]
    assert CUSTODY.next_states("at_intake") == ["in_vault"]
    assert CUSTODY.next_states("in_vault") == ["in_transit"]
    assert CUSTODY.is_final("with_buyer")


def test_verification_ends_verified_or_not_authentic() -> None:
    assert VERIFICATION.next_states("unverified") == ["not_authentic", "verified"]
    assert VERIFICATION.is_final("verified")
    assert VERIFICATION.is_final("not_authentic")


def test_a_piece_walks_the_whole_custody_path(staff: User) -> None:
    piece = make_piece()

    for status in ("in_transit", "at_intake", "in_vault", "in_transit", "with_buyer"):
        services.move_custody(piece, to=status, by=staff)

    piece.refresh_from_db()
    assert piece.custody_status == "with_buyer"


@pytest.mark.parametrize(
    ("start", "target"),
    [("with_owner", "in_vault"), ("in_vault", "with_buyer"), ("with_buyer", "in_transit")],
)
def test_a_piece_cannot_skip_a_step(staff: User, start: str, target: str) -> None:
    piece = make_piece()
    Piece.objects.filter(pk=piece.pk).update(custody_status=start)

    with pytest.raises(IllegalTransitionError) as error:
        services.move_custody(piece, to=target, by=staff)

    assert str(error.value) == f"A piece's custody cannot go from {start} to {target}."
    piece.refresh_from_db()
    assert piece.custody_status == start


def test_moves_read_the_status_from_the_database(staff: User) -> None:
    """A stale copy in memory must not decide the move."""
    piece = make_piece()
    stale = Piece.objects.get(pk=piece.pk)
    services.move_custody(piece, to="in_transit", by=staff)

    services.move_custody(stale, to="at_intake", by=staff)

    with pytest.raises(IllegalTransitionError):
        services.move_custody(stale, to="at_intake", by=staff)


def test_move_returns_the_fresh_piece_and_updates_the_copy_given(staff: User) -> None:
    piece = make_piece()

    moved = services.move_custody(piece, to="in_transit", by=staff)

    assert moved.custody_status == "in_transit"
    assert piece.custody_status == "in_transit"


@pytest.mark.parametrize("result", ["verified", "not_authentic"])
def test_verification_is_decided_once(staff: User, result: str) -> None:
    piece = make_piece()

    services.set_verification(piece, to=result, by=staff)

    piece.refresh_from_db()
    assert piece.verification_status == result
    with pytest.raises(IllegalTransitionError):
        services.set_verification(piece, to="verified", by=staff)
