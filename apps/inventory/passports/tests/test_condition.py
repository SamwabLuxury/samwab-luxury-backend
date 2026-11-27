"""Condition reports and restorations: the piece's history on its passport.

A condition report is a grade, a short summary and a list of flaws (what, how bad,
where, a sentence, and the photo that shows it). The newest report sets the piece's
grade. Reports are never edited: a new look at the piece is a new report.
"""

import pytest
from django.core.exceptions import ValidationError

from apps.inventory.catalog.tests.helpers import make_category
from apps.inventory.passports import services
from apps.inventory.passports.flaws import parse_flaws
from apps.inventory.passports.models import ConditionReport, Restoration
from apps.inventory.passports.tests.helpers import a_piece, checker
from apps.inventory.pieces.models import Piece
from apps.platform.audit.models import AuditEvent
from apps.shop.listings.tests.helpers import give_photo

pytestmark = pytest.mark.django_db

FLAW = {"type": "corner_rub", "severity": "minor", "where": "Base, front left", "note": "Light."}


def bag_piece() -> Piece:
    return a_piece(category=make_category("Totes", flaw_types=["corner_rub", "pilling"]))


def test_a_report_sets_the_piece_grade() -> None:
    piece = a_piece(condition_grade="new")

    report = services.add_condition_report(
        piece, grade="excellent", summary="Barely used.", flaws=[], by=checker()
    )

    piece.refresh_from_db()
    assert piece.condition_grade == "excellent"
    assert (report.grade, report.summary, report.graded_by) == (
        "excellent",
        "Barely used.",
        checker(),
    )


def test_flaws_are_kept_in_order_with_their_photo() -> None:
    piece = bag_piece()
    photo = give_photo(piece, kind="flaw")

    report = services.add_condition_report(
        piece,
        grade="very_good",
        summary="",
        flaws=[{**FLAW, "photo_id": str(photo.pk)}, {**FLAW, "type": "pilling", "note": ""}],
        by=checker(),
    )

    assert report.flaws == [
        {
            "type": "corner_rub",
            "severity": "minor",
            "where": "Base, front left",
            "note": "Light.",
            "photo_id": str(photo.pk),
        },
        {
            "type": "pilling",
            "severity": "minor",
            "where": "Base, front left",
            "note": "",
            "photo_id": None,
        },
    ]


@pytest.mark.parametrize(
    ("flaw", "message"),
    [
        ({**FLAW, "type": "scratch"}, "is not a flaw recorded for"),
        ({**FLAW, "severity": "awful"}, "minor, moderate or major"),
        ({**FLAW, "where": ""}, "where"),
        ({**FLAW, "where": "x" * 81}, "where"),
        ({**FLAW, "note": "x" * 301}, "note"),
        ({**FLAW, "photo_id": "00000000-0000-0000-0000-000000000000"}, "photo"),
    ],
)
def test_bad_flaws_are_refused(flaw: dict[str, str], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        services.add_condition_report(
            bag_piece(), grade="good", summary="", flaws=[flaw], by=checker()
        )

    assert not ConditionReport.objects.exists()


def test_another_pieces_photo_is_refused() -> None:
    other_photo = give_photo(a_piece(), kind="flaw")

    with pytest.raises(ValidationError, match="photo"):
        services.add_condition_report(
            bag_piece(),
            grade="good",
            summary="",
            flaws=[{**FLAW, "photo_id": str(other_photo.pk)}],
            by=checker(),
        )


def test_a_category_without_a_flaw_list_takes_any_lowercase_code() -> None:
    report = services.add_condition_report(
        a_piece(),
        grade="good",
        summary="",
        flaws=[{**FLAW, "type": "loose_thread"}],
        by=checker(),
    )

    assert report.flaws[0]["type"] == "loose_thread"


def test_a_flaw_code_must_be_lowercase() -> None:
    with pytest.raises(ValidationError, match="lowercase"):
        services.add_condition_report(
            a_piece(),
            grade="good",
            summary="",
            flaws=[{**FLAW, "type": "Loose thread"}],
            by=checker(),
        )


def test_an_unknown_grade_is_refused() -> None:
    with pytest.raises(ValidationError):
        services.add_condition_report(a_piece(), grade="A", summary="", flaws=[], by=checker())


def test_a_report_is_audited_on_the_piece_and_the_report() -> None:
    piece = a_piece(condition_grade="new")
    report = services.add_condition_report(piece, grade="good", summary="", flaws=[], by=checker())

    assert AuditEvent.objects.filter(
        action="passports.conditionreport.created", object_id=report.pk
    )
    graded = AuditEvent.objects.get(action="pieces.piece.changed", object_id=piece.pk)
    assert graded.changes == {"condition_grade": {"from": "new", "to": "good"}}


# ---------- the flaw lines staff type in the admin ----------


def test_one_flaw_per_line_from_the_admin() -> None:
    text = "corner_rub | minor | Base, front left | Light rubbing.\r\n\n pilling|moderate|Handle\n"

    assert parse_flaws(text) == [
        {
            "type": "corner_rub",
            "severity": "minor",
            "where": "Base, front left",
            "note": "Light rubbing.",
        },
        {"type": "pilling", "severity": "moderate", "where": "Handle", "note": ""},
    ]


def test_a_line_with_too_few_parts_is_refused() -> None:
    with pytest.raises(ValidationError, match="Line 2"):
        parse_flaws("corner_rub | minor | Base\npilling | minor")


# ---------- restorations ----------


def test_a_restoration_is_recorded_and_audited() -> None:
    piece = a_piece()

    restoration = services.add_restoration(
        piece,
        description="Edge paint redone on both handles.",
        performed_by="Atelier Lagos",
        performed_on=None,
        cost_minor=12_000,
        by=checker(),
    )

    assert Restoration.objects.get() == restoration
    assert restoration.currency == "USD"
    assert AuditEvent.objects.filter(action="passports.restoration.created").exists()
    assert str(restoration) == "Edge paint redone on both handles."
