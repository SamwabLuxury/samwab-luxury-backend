"""Tests for the JSON Schema helpers: categories and designs describe piece attributes."""

from typing import Any

import pytest

from apps.core.json_schema import attribute_errors, schema_errors

SIZE = {
    "type": "object",
    "properties": {
        "width_cm": {"type": "number", "minimum": 1},
        "hardware": {"enum": ["gold", "palladium"]},
    },
    "required": ["width_cm"],
}


@pytest.mark.parametrize("schema", [{}, SIZE, {"type": "object", "additionalProperties": False}])
def test_a_valid_schema_has_no_errors(schema: dict[str, Any]) -> None:
    assert schema_errors(schema) == []


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "banana"},
        {"properties": {"width_cm": {"minimum": "one"}}},
        {"required": "width_cm"},
    ],
)
def test_a_broken_schema_says_what_is_wrong(schema: dict[str, Any]) -> None:
    errors = schema_errors(schema)

    assert len(errors) == 1
    assert errors[0]


def test_attributes_that_pass() -> None:
    assert attribute_errors(SIZE, {"width_cm": 28, "hardware": "gold"}) == []


def test_every_problem_is_listed_with_where_it_is() -> None:
    errors = attribute_errors(SIZE, {"width_cm": 0, "hardware": "silver"})

    assert errors == [
        ("hardware", "'silver' is not one of ['gold', 'palladium']"),
        ("width_cm", "0 is less than the minimum of 1"),
    ]


def test_a_missing_required_attribute_is_reported_on_the_whole_object() -> None:
    assert attribute_errors(SIZE, {}) == [("", "'width_cm' is a required property")]


def test_nested_paths_use_dots() -> None:
    schema = {
        "type": "object",
        "properties": {
            "stones": {"type": "array", "items": {"type": "object", "required": ["carat"]}}
        },
    }

    assert attribute_errors(schema, {"stones": [{"carat": 1}, {}]}) == [
        ("stones.1", "'carat' is a required property")
    ]


def test_an_empty_schema_accepts_anything() -> None:
    assert attribute_errors({}, {"anything": ["at", "all"]}) == []
