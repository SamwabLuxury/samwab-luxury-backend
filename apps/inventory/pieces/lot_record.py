"""The lot record (E7): the piece's facts as rows the piece page shows as they are.

First the facts every piece has (maker, model, year, size, grade), then its
attributes, sorted by key so the order is the same on every database (PostgreSQL's
jsonb does not keep the order keys were written in). A row is named by the JSON
Schema ``title`` of its attribute, from the design first, then the category; with
no title, the key is turned into words ("size_cm" -> "Size cm").

Only public facts: the serial or date code, costs, owner and staff notes live in
their own columns and are never read here.
"""

from typing import Any, TypedDict

from apps.inventory.pieces.models import Piece


class Row(TypedDict):
    label: str
    value: str


def lot_record(piece: Piece) -> list[Row]:
    rows: list[Row] = [{"label": "Maker", "value": piece.brand.name}]
    if piece.product_model:
        rows.append({"label": "Model", "value": piece.product_model.name})
    if piece.production_year:
        rows.append({"label": "Year", "value": str(piece.production_year)})
    if piece.size_label:
        rows.append({"label": "Size", "value": piece.size_label})
    if piece.condition_grade:
        rows.append({"label": "Grade", "value": piece.get_condition_grade_display()})

    titles = _titles(piece)
    attributes = piece.attributes if isinstance(piece.attributes, dict) else {}
    for key in sorted(attributes):
        value = _words(attributes[key])
        if value:
            rows.append({"label": titles.get(key) or _name(key), "value": value})
    return rows


def _titles(piece: Piece) -> dict[str, str]:
    titles = _schema_titles(piece.category.attribute_schema)
    if piece.product_model:
        titles.update(_schema_titles(piece.product_model.attribute_schema))
    return titles


def _schema_titles(schema: Any) -> dict[str, str]:
    properties = schema.get("properties") if isinstance(schema, dict) else None
    if not isinstance(properties, dict):
        return {}
    return {
        key: rule["title"]
        for key, rule in properties.items()
        if isinstance(rule, dict) and isinstance(rule.get("title"), str) and rule["title"]
    }


def _name(key: str) -> str:
    return key.replace("_", " ").strip().capitalize()


def _words(value: Any) -> str:
    """An attribute's value as text; empty means "leave the row out"."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, list):
        return ", ".join(word for word in (_words(item) for item in value) if word)
    if isinstance(value, dict):
        parts = (f"{_name(key).lower()} {_words(value[key])}" for key in sorted(value))
        return ", ".join(part for part in parts if not part.endswith(" "))
    return str(value).strip()
