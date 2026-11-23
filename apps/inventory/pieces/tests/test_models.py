"""Tests for the pieces table: the rules the database and the admin enforce."""

from typing import Any

import pytest
from django.core.exceptions import ValidationError
from django.db import DataError, IntegrityError, transaction
from django.db.models import ProtectedError

from apps.inventory.catalog.tests.helpers import (
    make_brand,
    make_category,
    make_material,
    make_product_model,
)
from apps.inventory.pieces.models import Piece, PieceMaterial
from apps.inventory.pieces.tests.helpers import make_house, make_owner, make_piece

pytestmark = pytest.mark.django_db


def messages(error: pytest.ExceptionInfo[ValidationError]) -> dict[str, list[str]]:
    return error.value.message_dict


def refuses(**fields: Any) -> None:
    # PostgreSQL refuses a value longer than its column (DataError) before any check;
    # SQLite does not enforce lengths, so the check constraint refuses it (IntegrityError).
    with pytest.raises((IntegrityError, DataError)), transaction.atomic():
        make_piece(**fields)


def unsaved(**fields: Any) -> Piece:
    """A piece that is built but not saved, to check the form rules."""
    piece = make_piece()
    for name, value in fields.items():
        setattr(piece, name, value)
    return piece


def test_table_names() -> None:
    assert Piece._meta.db_table == "pieces"
    assert PieceMaterial._meta.db_table == "piece_materials"


def test_piece_defaults() -> None:
    piece = make_piece(title="Kelly 28, Gold Togo")

    assert piece.verification_status == "unverified"
    assert piece.custody_status == "with_owner"
    assert piece.currency == "USD"
    assert piece.attributes == {}
    assert piece.product_model is None
    assert piece.size_system == ""
    assert piece.serial_or_date_code == ""
    assert piece.acquisition_cost_minor is None
    assert piece.storage_free_until is None
    assert str(piece) == "Kelly 28, Gold Togo"


def test_a_piece_has_materials() -> None:
    togo, gold = make_material("Togo leather"), make_material("Gold-plated hardware")
    piece = make_piece()

    piece.materials.set([togo, gold])

    assert set(piece.materials.all()) == {togo, gold}
    assert list(togo.pieces.all()) == [piece]


def test_a_material_in_use_cannot_be_deleted() -> None:
    togo = make_material("Togo leather")
    make_piece().materials.add(togo)

    with pytest.raises(ProtectedError):
        togo.delete()


def test_the_same_material_is_listed_once() -> None:
    togo = make_material("Togo leather")
    piece = make_piece()

    piece.materials.add(togo)
    piece.materials.add(togo)

    assert piece.materials.count() == 1


def test_catalog_rows_with_pieces_cannot_be_deleted() -> None:
    piece = make_piece(product_model=make_product_model())

    for row in (piece.brand, piece.category, piece.product_model):
        with pytest.raises(ProtectedError):
            row.delete()  # type: ignore[union-attr]


def test_an_owner_with_pieces_cannot_be_deleted() -> None:
    piece = make_piece()

    with pytest.raises(ProtectedError):
        piece.current_owner.delete()


# ---------- database rules ----------


@pytest.mark.parametrize(
    "fields",
    [
        {"department": "kids"},
        {"size_system": "XX"},
        {"source": "found"},
        {"authentication_basis": "gut_feeling"},
        {"condition_grade": "mint"},
        {"currency": "EUR"},
        {"home_country": "us"},
        {"home_country": "USA"},
        {"home_country": ""},
    ],
)
def test_database_refuses_unknown_values(fields: dict[str, Any]) -> None:
    refuses(**fields)


def test_database_refuses_an_unknown_status() -> None:
    piece = make_piece()

    for field in ("verification_status", "custody_status"):
        with pytest.raises(IntegrityError), transaction.atomic():
            Piece.objects.filter(pk=piece.pk).update(**{field: "lost"})


def test_an_acquisition_cost_is_for_house_stock_only() -> None:
    refuses(source="consigned", acquisition_cost_minor=500_000)


def test_house_stock_keeps_its_acquisition_cost() -> None:
    piece = make_piece(source="house_stock", acquisition_cost_minor=900_000_00)
    piece.refresh_from_db()

    assert piece.acquisition_cost_minor == 900_000_00


# ---------- form rules ----------


def test_the_design_must_match_the_brand_and_category() -> None:
    kelly = make_product_model("Kelly 28")
    piece = make_piece(brand=make_brand("Chanel"), category=make_category("Shoes"))
    piece.product_model = kelly

    with pytest.raises(ValidationError) as error:
        piece.full_clean()

    assert set(messages(error)) == {"brand", "category"}


def test_a_piece_needs_an_owner() -> None:
    kelly = make_product_model("Kelly 28", department="women")
    piece = Piece(
        product_model=kelly,
        brand=kelly.brand,
        category=kelly.category,
        title="Kelly 28",
        source="house_stock",
        home_country="US",
    )

    with pytest.raises(ValidationError) as error:
        piece.full_clean()

    assert "current_owner" in messages(error)


def test_house_stock_belongs_to_a_house_account() -> None:
    piece = unsaved(source="house_stock", current_owner=make_owner())

    with pytest.raises(ValidationError) as error:
        piece.full_clean()

    assert "current_owner" in messages(error)


def test_a_consigned_piece_belongs_to_a_person_not_the_house() -> None:
    piece = unsaved(source="consigned", current_owner=make_house())

    with pytest.raises(ValidationError) as error:
        piece.full_clean()

    assert "current_owner" in messages(error)


def test_a_consigned_piece_has_no_acquisition_cost_in_the_form() -> None:
    piece = unsaved(source="consigned", current_owner=make_owner(), acquisition_cost_minor=100)

    with pytest.raises(ValidationError) as error:
        piece.full_clean()

    assert "acquisition_cost_minor" in messages(error)


def test_a_size_system_needs_a_size_label() -> None:
    piece = unsaved(size_system="EU", size_label="")

    with pytest.raises(ValidationError) as error:
        piece.full_clean()

    assert "size_label" in messages(error)


@pytest.mark.parametrize(
    ("year", "valid"), [(1956, True), (1799, False), (3000, False), (None, True)]
)
def test_production_year_must_make_sense(year: int | None, valid: bool) -> None:
    piece = unsaved(production_year=year)

    if valid:
        piece.full_clean()
    else:
        with pytest.raises(ValidationError) as error:
            piece.full_clean()
        assert "production_year" in messages(error)


def test_hs_code_and_country_formats() -> None:
    piece = unsaved(hs_code="42.02", home_country="Nigeria")

    with pytest.raises(ValidationError) as error:
        piece.full_clean()

    assert {"hs_code", "home_country"} <= set(messages(error))


class TestAttributes:
    """Attributes are checked against the category's schema and the design's schema."""

    @pytest.fixture
    def kelly(self) -> Any:
        bags = make_category(
            "Bags",
            attribute_schema={
                "type": "object",
                "properties": {"width_cm": {"type": "number", "minimum": 1}},
                "required": ["width_cm"],
            },
        )
        return make_product_model(
            "Kelly 28",
            category=bags,
            attribute_schema={"properties": {"hardware": {"enum": ["gold", "palladium"]}}},
        )

    def test_attributes_that_pass_both_schemas(self, kelly: Any) -> None:
        piece = make_piece(product_model=kelly, attributes={"width_cm": 28, "hardware": "gold"})

        piece.full_clean()

    def test_the_category_schema_applies(self, kelly: Any) -> None:
        piece = make_piece(product_model=kelly, attributes={"width_cm": 0})

        with pytest.raises(ValidationError) as error:
            piece.full_clean()

        assert messages(error)["attributes"] == ["width_cm: 0 is less than the minimum of 1"]

    def test_the_design_schema_applies_too(self, kelly: Any) -> None:
        piece = make_piece(product_model=kelly, attributes={"width_cm": 28, "hardware": "silver"})

        with pytest.raises(ValidationError) as error:
            piece.full_clean()

        assert messages(error)["attributes"] == [
            "hardware: 'silver' is not one of ['gold', 'palladium']"
        ]

    def test_every_problem_is_reported(self, kelly: Any) -> None:
        piece = make_piece(product_model=kelly, attributes={"hardware": "silver"})

        with pytest.raises(ValidationError) as error:
            piece.full_clean()

        assert messages(error)["attributes"] == [
            "'width_cm' is a required property",
            "hardware: 'silver' is not one of ['gold', 'palladium']",
        ]

    def test_attributes_must_be_an_object(self) -> None:
        piece = unsaved(attributes=["width_cm", 28])

        with pytest.raises(ValidationError) as error:
            piece.full_clean()

        assert "attributes" in messages(error)

    def test_a_piece_without_a_design_uses_only_the_category_schema(self, kelly: Any) -> None:
        piece = make_piece(
            brand=kelly.brand, category=kelly.category, attributes={"width_cm": 30, "hardware": "x"}
        )

        piece.full_clean()
