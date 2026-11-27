"""Passports: a piece verified by Samwab gets a numbered passport with an unguessable link.

The passport number is printed on the card ("Nº 0042 17"); the public code goes in the
QR link. Verifying a piece and issuing its passport happen together.
"""

import re

import pytest
from django.db import IntegrityError, transaction

from apps.inventory.passports import selectors, services
from apps.inventory.passports.exceptions import PieceNotAuthenticError
from apps.inventory.passports.models import Passport
from apps.inventory.passports.tests.helpers import a_piece, checker, verified
from apps.inventory.pieces.enums import VerificationStatus
from apps.platform.audit.models import AuditEvent
from apps.platform.core.state_machine import IllegalTransitionError

pytestmark = pytest.mark.django_db


def test_verifying_a_piece_issues_its_passport() -> None:
    piece = a_piece()

    passport = verified(piece)

    piece.refresh_from_db()
    assert piece.verification_status == VerificationStatus.VERIFIED
    assert passport.piece == piece
    assert passport.passport_number == 1
    assert passport.is_public
    assert re.fullmatch(r"[2-9A-HJ-NP-Z]{10}", passport.public_code)


def test_numbers_count_up_and_codes_differ() -> None:
    first, second = verified(a_piece()), verified(a_piece())

    assert (first.passport_number, second.passport_number) == (1, 2)
    assert first.public_code != second.public_code


def test_the_number_as_printed_on_the_card() -> None:
    passport = verified(a_piece())

    assert passport.printed_number == "0000 01"
    passport.passport_number = 4217
    assert passport.printed_number == "0042 17"
    passport.passport_number = 1_234_567
    assert passport.printed_number == "12345 67"


def test_issuing_twice_returns_the_same_passport() -> None:
    piece = a_piece()
    passport = verified(piece)

    again = services.issue_passport(piece, by=checker())

    assert again == passport
    assert Passport.objects.count() == 1


def test_a_piece_found_not_authentic_gets_no_passport() -> None:
    piece = a_piece()
    services.mark_not_authentic(piece, by=checker())

    with pytest.raises(PieceNotAuthenticError):
        services.issue_passport(piece, by=checker())
    with pytest.raises(IllegalTransitionError):
        services.verify(piece, by=checker())  # the result is recorded once

    assert not Passport.objects.exists()


def test_an_unverified_piece_gets_no_passport() -> None:
    with pytest.raises(PieceNotAuthenticError):
        services.issue_passport(a_piece(), by=checker())


def test_a_number_already_taken_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    taken = verified(a_piece())
    calls = iter([taken.passport_number, taken.passport_number + 1])
    monkeypatch.setattr(services, "_next_number", lambda: next(calls))

    passport = verified(a_piece())

    assert passport.passport_number == 2  # a second checker took 1 a moment earlier


def test_the_database_refuses_a_second_passport_for_a_piece() -> None:
    passport = verified(a_piece())

    with pytest.raises(IntegrityError), transaction.atomic():
        Passport.objects.create(piece=passport.piece, passport_number=99, public_code="ABCDEFGHJK")


def test_hiding_and_showing_a_passport() -> None:
    passport = verified(a_piece())

    services.set_public(passport, False, by=checker())
    assert selectors.public_passport(passport.public_code) is None

    services.set_public(passport, True, by=checker())
    assert selectors.public_passport(passport.public_code.lower()) == passport


def test_everything_is_in_the_audit_log() -> None:
    piece = a_piece()
    passport = verified(piece)
    services.set_public(passport, False, by=checker())

    actions = set(AuditEvent.objects.values_list("action", flat=True))
    assert {
        "pieces.piece.verification_set",
        "passports.passport.issued",
        "passports.passport.changed",
    } <= actions
    issued = AuditEvent.objects.get(action="passports.passport.issued")
    assert issued.changes["passport_number"] == 1
    assert issued.actor == checker()


def test_str() -> None:
    assert str(verified(a_piece())) == "Passport Nº 0000 01"
