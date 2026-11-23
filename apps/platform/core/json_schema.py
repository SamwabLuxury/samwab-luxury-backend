"""Check JSON Schemas, and check data against them.

Categories and designs describe a piece's attributes (measurements, metal,
hardware) with a JSON Schema. Schemas follow draft 2020-12, the latest draft
the ``jsonschema`` package supports. ``format`` is not checked.
"""

from typing import Any

from jsonschema import Draft202012Validator


def schema_errors(schema: Any) -> list[str]:
    """What is wrong with a schema itself. An empty list means it is a valid schema."""
    validator = Draft202012Validator(Draft202012Validator.META_SCHEMA)
    best = sorted(validator.iter_errors(schema), key=lambda error: list(error.path))
    return [best[0].message] if best else []


def attribute_errors(schema: dict[str, Any], data: Any) -> list[tuple[str, str]]:
    """Every way ``data`` breaks ``schema``, as (where, message), sorted by where.

    ``where`` is a dotted path such as ``stones.1``; an empty string means the
    whole object (for example a missing required attribute).
    """
    validator = Draft202012Validator(schema)
    found = [
        (".".join(str(part) for part in error.absolute_path), error.message)
        for error in validator.iter_errors(data)
    ]
    return sorted(found)
