"""E8: a comparable sale's grade is one of the five grades pieces use.

The price explainer matches sales to a piece by grade, so free text ("v. good",
"Excellent ") would silently miss. The grades now live in the catalog app, and the
pieces app reuses them, so catalog never depends on pieces.
"""

from importlib import import_module

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.inventory.catalog.enums import ConditionGrade
from apps.inventory.catalog.models import ComparableSale
from apps.inventory.catalog.tests.helpers import make_sale
from apps.inventory.pieces import enums as piece_enums

pytestmark = pytest.mark.django_db


def test_pieces_and_comparable_sales_share_one_grade_scale() -> None:
    assert piece_enums.ConditionGrade is ConditionGrade
    assert ConditionGrade.values == ["new", "excellent", "very_good", "good", "fair"]


@pytest.mark.parametrize("grade", ["new", "excellent", "very_good", "good", "fair", ""])
def test_a_sale_takes_a_known_grade_or_none(grade: str) -> None:
    sale = make_sale(condition_grade=grade)

    sale.full_clean()


def test_an_unknown_grade_is_refused_by_the_form_rules() -> None:
    sale = make_sale()
    sale.condition_grade = "Very good"  # the label, not the value

    with pytest.raises(ValidationError) as refused:
        sale.full_clean()

    assert "condition_grade" in refused.value.message_dict


def test_an_unknown_grade_is_refused_by_the_database() -> None:
    sale = make_sale()

    with pytest.raises(IntegrityError), transaction.atomic():
        ComparableSale.objects.filter(pk=sale.pk).update(condition_grade="mint")


# ---------- the one-time conversion of grades typed as free text before E8 ----------

normalise = import_module(
    "apps.inventory.catalog.migrations.0003_comparable_sale_grades"
).normalise_grade


@pytest.mark.parametrize(
    ("typed", "stored"),
    [
        ("excellent", "excellent"),
        ("Excellent", "excellent"),
        ("  EXCELLENT ", "excellent"),
        ("Very good", "very_good"),
        ("very good", "very_good"),
        ("very-good", "very_good"),
        ("very_good", "very_good"),
        ("New", "new"),
        ("Fair", "fair"),
        ("", ""),
        ("B", ""),  # a letter grade (the old design): cannot be read safely
        ("v. good", ""),
        ("Mint", ""),
    ],
)
def test_typed_grades_are_converted_or_cleared(typed: str, stored: str) -> None:
    assert normalise(typed) == stored
