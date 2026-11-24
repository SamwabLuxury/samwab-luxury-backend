"""The lot record's shaping rules, on their own (the API test covers a full piece)."""

from typing import Any

import pytest

from apps.inventory.catalog.models import Brand, Category
from apps.inventory.pieces.lot_record import Row, lot_record
from apps.inventory.pieces.models import Piece


def piece(attributes: Any, schema: Any = None) -> Piece:
    """An unsaved piece: the lot record only reads it."""
    return Piece(
        brand=Brand(name="Chanel", slug="chanel"),
        category=Category(name="Bags", slug="bags", attribute_schema=schema or {}),
        attributes=attributes,
    )


def rows_after_maker(attributes: Any, schema: Any = None) -> list[Row]:
    record = lot_record(piece(attributes, schema))
    assert record[0] == {"label": "Maker", "value": "Chanel"}
    return record[1:]


@pytest.mark.parametrize("empty", [None, "", "   ", [], [None, ""], {}, {"width": None}])
def test_empty_values_leave_their_row_out(empty: Any) -> None:
    assert rows_after_maker({"lining": empty}) == []


def test_yes_and_no_numbers_and_lists() -> None:
    assert rows_after_maker({"boxed": False, "weight_g": 640, "colours": ["black", 2]}) == [
        {"label": "Boxed", "value": "No"},
        {"label": "Colours", "value": "black, 2"},
        {"label": "Weight g", "value": "640"},
    ]


def test_a_part_of_an_object_without_a_value_is_left_out() -> None:
    assert rows_after_maker({"size_cm": {"width": 28, "depth": None}}) == [
        {"label": "Size cm", "value": "width 28"}
    ]


@pytest.mark.parametrize(
    "schema",
    [
        {"properties": "not a dict"},
        {"properties": {"lining": "not a dict"}},
        {"properties": {"lining": {"title": ""}}},
        {"properties": {"lining": {"title": 3}}},
        ["not", "a", "schema"],
    ],
)
def test_a_schema_without_a_usable_title_falls_back_to_the_key(schema: Any) -> None:
    assert rows_after_maker({"lining": "Lambskin"}, schema) == [
        {"label": "Lining", "value": "Lambskin"}
    ]


def test_attributes_that_are_not_an_object_are_ignored() -> None:
    assert rows_after_maker(["not", "an", "object"]) == []
