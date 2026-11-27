"""Passports in the admin: reviewers verify pieces (which issues the passport), intake
staff record condition reports and restorations.
"""

from typing import Any

import pytest
from django.contrib.messages import get_messages
from django.test import Client

from apps.inventory.passports import services
from apps.inventory.passports.models import ConditionReport, Passport, Restoration
from apps.inventory.passports.tests.helpers import a_piece, checker, verified
from apps.users.accounts import roles
from apps.users.accounts.tests.helpers import admin_login, make_staff

pytestmark = pytest.mark.django_db


def as_role(client: Client, role: str) -> Client:
    admin_login(client, make_staff(f"{role}@samwab.com", role))
    return client


def notes(response: Any) -> list[str]:
    return [str(message) for message in get_messages(response.wsgi_request)]


def act(client: Client, action: str, *pieces: Any) -> Any:
    return client.post(
        "/admin/pieces/piece/",
        {"action": action, "_selected_action": [str(piece.pk) for piece in pieces]},
        follow=True,
    )


def test_a_reviewer_verifies_a_piece_and_its_passport_is_issued(client: Client) -> None:
    piece = a_piece()

    response = act(as_role(client, roles.REVIEWER), "verify_selected", piece)

    passport = Passport.objects.get(piece=piece)
    assert any(f"Nº {passport.printed_number}" in note for note in notes(response))


def test_a_reviewer_marks_a_piece_not_authentic(client: Client) -> None:
    piece = a_piece()

    act(as_role(client, roles.REVIEWER), "mark_not_authentic_selected", piece)

    piece.refresh_from_db()
    assert piece.verification_status == "not_authentic"
    assert not Passport.objects.exists()


def test_a_result_is_recorded_once(client: Client) -> None:
    piece = a_piece()
    verified(piece)

    response = act(as_role(client, roles.REVIEWER), "mark_not_authentic_selected", piece)

    piece.refresh_from_db()
    assert piece.verification_status == "verified"
    assert any("cannot" in note for note in notes(response))


def test_verifying_twice_changes_nothing(client: Client) -> None:
    piece = a_piece()
    verified(piece)

    response = act(as_role(client, roles.REVIEWER), "verify_selected", piece)

    assert Passport.objects.count() == 1
    assert any("already recorded (verified)" in note for note in notes(response))


def test_intake_staff_cannot_verify(client: Client) -> None:
    page = as_role(client, roles.INTAKE_STAFF).get("/admin/pieces/piece/")

    choices = [choice[0] for choice in page.context["action_form"].fields["action"].choices]
    assert "verify_selected" not in choices
    assert "put_in_vault" in choices


def test_intake_staff_record_a_condition_report_with_flaw_lines(client: Client) -> None:
    piece = a_piece(condition_grade="new")

    response = as_role(client, roles.INTAKE_STAFF).post(
        "/admin/passports/conditionreport/add/",
        {
            "piece": str(piece.pk),
            "grade": "very_good",
            "summary": "Light wear.",
            "flaw_lines": "corner_rub | minor | Base, front left | Light rubbing.",
        },
    )

    assert response.status_code == 302, response.content
    report = ConditionReport.objects.get()
    assert report.flaws[0]["where"] == "Base, front left"
    piece.refresh_from_db()
    assert piece.condition_grade == "very_good"


def test_a_bad_flaw_line_shows_on_the_form(client: Client) -> None:
    response = as_role(client, roles.INTAKE_STAFF).post(
        "/admin/passports/conditionreport/add/",
        {"piece": str(a_piece().pk), "grade": "good", "summary": "", "flaw_lines": "pilling"},
    )

    assert response.status_code == 200
    assert "Line 1" in response.content.decode()
    assert not ConditionReport.objects.exists()


def test_a_condition_report_cannot_be_changed_or_deleted(client: Client) -> None:
    as_role(client, roles.INTAKE_STAFF).post(
        "/admin/passports/conditionreport/add/",
        {"piece": str(a_piece().pk), "grade": "good", "summary": "", "flaw_lines": ""},
    )
    report = ConditionReport.objects.get()

    page = client.get(f"/admin/passports/conditionreport/{report.pk}/change/")

    assert page.context["has_change_permission"] is False
    assert page.context["has_delete_permission"] is False


def test_intake_staff_record_a_restoration(client: Client) -> None:
    piece = a_piece()

    response = as_role(client, roles.INTAKE_STAFF).post(
        "/admin/passports/restoration/add/",
        {
            "piece": str(piece.pk),
            "description": "Edge paint redone.",
            "performed_by": "Atelier Lagos",
            "performed_on": "2026-10-02",
            "cost_minor": "120.00",
        },
    )

    assert response.status_code == 302, response.content
    restoration = Restoration.objects.get()
    assert restoration.cost_minor == 12_000  # typed in dollars

    client.post(
        f"/admin/passports/restoration/{restoration.pk}/change/",
        {
            "piece": str(piece.pk),
            "description": "Edge paint redone on both handles.",
            "performed_by": "Atelier Lagos",
            "performed_on": "2026-10-02",
            "cost_minor": "125",
        },
    )
    restoration.refresh_from_db()
    assert restoration.cost_minor == 12_500
    assert restoration.description.endswith("both handles.")


def test_a_passport_can_be_hidden_from_its_screen(client: Client) -> None:
    passport = verified(a_piece())

    response = as_role(client, roles.INTAKE_STAFF).post(
        f"/admin/passports/passport/{passport.pk}/change/", {"is_public": ""}
    )

    assert response.status_code == 302, response.content
    passport.refresh_from_db()
    assert passport.is_public is False


def test_passports_are_never_added_or_deleted_by_hand(client: Client) -> None:
    passport = verified(a_piece())
    as_role(client, roles.INTAKE_STAFF)

    assert client.get("/admin/passports/passport/add/").status_code == 403
    page = client.get(f"/admin/passports/passport/{passport.pk}/change/")
    assert page.context["has_delete_permission"] is False


@pytest.mark.parametrize("screen", ["passport", "conditionreport", "restoration"])
def test_the_screens_open_for_intake_staff(client: Client, screen: str) -> None:
    piece = a_piece()
    verified(piece)
    services.add_condition_report(piece, grade="good", summary="", flaws=[], by=checker())

    assert as_role(client, roles.INTAKE_STAFF).get(f"/admin/passports/{screen}/").status_code == 200


def test_the_menu_lists_passports(client: Client) -> None:
    text = as_role(client, roles.INTAKE_STAFF).get("/admin/").content.decode()

    assert "Passports" in text
    assert "Condition reports" in text
