"""Money boxes in the admin read and show US dollars; the database keeps cents (E16).

Every money column is a whole number of US cents (``*_minor``). Typing cents is easy
to get wrong by a factor of 100, so admin forms use ``DollarsField``: staff type
12,500.00 (or 12500, or $12,500) and the form hands the model 1250000.

``DollarsAdmin`` is a mixin for a ModelAdmin or inline: list each cents column with
its plain label in ``dollar_fields`` and its box becomes a dollar box.
"""

import re
from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from typing import Any

from django import forms
from django.contrib import admin
from django.db import models
from django.http import HttpRequest

from apps.platform.core.admin_look import TextInput
from apps.platform.core.money import Money

TYPE_DOLLARS = "Enter an amount in dollars, such as 12,500.00."
DOLLARS_HELP = "In US dollars, such as 12,500.00."
_SHAPE = re.compile(r"^\d{1,3}(,\d{3})*(\.\d+)?$|^\d+(\.\d+)?$")


def cents_as_dollars(cents: int) -> str:
    """1250000 -> "12,500.00"."""
    return f"{cents // 100:,}.{cents % 100:02d}"


class DollarsField(forms.CharField):
    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("help_text", DOLLARS_HELP)
        kwargs.setdefault("widget", TextInput(attrs={"prefix": "$", "inputmode": "decimal"}))
        super().__init__(**kwargs)

    def prepare_value(self, value: Any) -> Any:
        if value is None:
            return ""
        if isinstance(value, int):
            return cents_as_dollars(value)
        return value  # text typed by staff, shown again after a form error

    def to_python(self, value: Any) -> int | None:  # type: ignore[override]
        text = (super().to_python(value) or "").strip().removeprefix("$").strip()
        if not text:
            return None
        if text.startswith("-"):
            raise forms.ValidationError("A price cannot be below zero.", code="negative")
        if not _SHAPE.match(text):
            raise forms.ValidationError(TYPE_DOLLARS, code="invalid")
        try:
            amount = Decimal(text.replace(",", ""))
        except InvalidOperation:
            raise forms.ValidationError(TYPE_DOLLARS, code="invalid") from None
        if amount.as_tuple().exponent < -2:  # type: ignore[operator]
            raise forms.ValidationError(
                "Use at most two digits after the point, such as 12,500.50.", code="cents"
            )
        return int(amount * 100)


class DollarsAdmin:
    """Mixin: ``dollar_fields = (("ask_minor", "Asking price"),)``."""

    dollar_fields: tuple[tuple[str, str], ...] = ()

    def formfield_for_dbfield(
        self, db_field: "models.Field[Any, Any]", request: HttpRequest, **kwargs: Any
    ) -> Any:
        label = dict(self.dollar_fields).get(db_field.name)
        if label is None:
            return super().formfield_for_dbfield(db_field, request, **kwargs)  # type: ignore[misc]
        return DollarsField(
            label=label, required=not (db_field.blank or db_field.null), help_text=DOLLARS_HELP
        )


def dollars_column(field: str, label: str) -> Callable[[Any, Any], str]:
    """A read-only admin column or field showing a cents column as "$12,500.00".

    Use as a class attribute: ``total = dollars_column("total_minor", "Total")``.
    """

    @admin.display(description=label, ordering=field)
    def show(model_admin: Any, row: Any) -> str:
        cents = getattr(row, field)
        if cents is None:
            return "-"
        return str(Money(cents, getattr(row, "currency", "USD")))

    return show
