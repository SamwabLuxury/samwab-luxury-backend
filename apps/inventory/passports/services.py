"""Changes to passports, condition reports and restorations. The admin calls these.

Verifying a piece and issuing its passport happen in one transaction, so a verified
piece always has a passport and only a verified piece has one.
"""

import secrets
from collections.abc import Iterable, Mapping
from datetime import date
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import Max

from apps.inventory.passports.exceptions import PieceNotAuthenticError
from apps.inventory.passports.flaws import checked_flaws
from apps.inventory.passports.models import ConditionReport, Passport, Restoration
from apps.inventory.pieces import services as pieces
from apps.inventory.pieces.enums import VerificationStatus
from apps.inventory.pieces.models import Piece
from apps.platform.audit import services as audit
from apps.users.accounts.models import User

# No 0/O or 1/I, so a code read aloud or typed from a card cannot be misread.
CODE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
CODE_LENGTH = 10  # 32**10, about a million million codes: not guessable
_NUMBER_TRIES = 5


def new_public_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def _next_number() -> int:
    return (Passport.objects.aggregate(last=Max("passport_number"))["last"] or 0) + 1


@transaction.atomic
def issue_passport(piece: Piece, *, by: User) -> Passport:
    """The piece's passport, issued now if it has none. Only verified pieces get one."""
    piece = Piece.objects.select_for_update(of=("self",)).get(pk=piece.pk)
    existing = Passport.objects.filter(piece=piece).first()
    if existing is not None:
        return existing
    if piece.verification_status != VerificationStatus.VERIFIED:
        raise PieceNotAuthenticError()
    for attempt in range(_NUMBER_TRIES):
        try:
            # Two checkers at once may pick the same next number; the unique index
            # refuses the second, which simply tries the number after.
            with transaction.atomic():
                passport = Passport.objects.create(
                    piece=piece, passport_number=_next_number(), public_code=new_public_code()
                )
            break
        except IntegrityError:
            if attempt == _NUMBER_TRIES - 1:  # pragma: no cover - five clashes in a row
                raise
    audit.record(
        "issued",
        passport,
        by=by,
        changes={"passport_number": passport.passport_number, "piece_id": str(piece.pk)},
    )
    return passport


@transaction.atomic
def verify(piece: Piece, *, by: User) -> Passport:
    """Record that Samwab found the piece authentic, and issue its passport."""
    pieces.set_verification(piece, to=VerificationStatus.VERIFIED, by=by)
    return issue_passport(piece, by=by)


def mark_not_authentic(piece: Piece, *, by: User) -> Piece:
    """Record that the piece is not authentic. It never gets a passport."""
    return pieces.set_verification(piece, to=VerificationStatus.NOT_AUTHENTIC, by=by)


@transaction.atomic
def set_public(passport: Passport, is_public: bool, *, by: User) -> Passport:
    """Show or hide the passport page (and its number on the shop)."""
    before = audit.snapshot(passport)
    passport.is_public = is_public
    passport.save(update_fields=["is_public"])
    audit.record_saved(passport, before=before, by=by)
    return passport


@transaction.atomic
def add_condition_report(
    piece: Piece,
    *,
    grade: str,
    summary: str,
    flaws: Iterable[Mapping[str, Any]],
    by: User,
) -> ConditionReport:
    """Record a new look at the piece. Its grade becomes the piece's grade."""
    report = ConditionReport(piece=piece, grade=grade, summary=summary.strip(), graded_by=by)
    report.flaws = checked_flaws(piece, flaws)
    report.full_clean()
    report.save()
    audit.record_saved(report, before=None, by=by)

    locked = Piece.objects.select_for_update(of=("self",)).get(pk=piece.pk)
    if locked.condition_grade != grade:
        before = audit.snapshot(locked)
        locked.condition_grade = grade
        locked.save(update_fields=["condition_grade", "updated_at"])
        audit.record_saved(locked, before=before, by=by)
    piece.condition_grade = grade
    return report


@transaction.atomic
def add_restoration(
    piece: Piece,
    *,
    description: str,
    performed_by: str,
    performed_on: date | None,
    cost_minor: int | None,
    by: User,
) -> Restoration:
    restoration = Restoration(
        piece=piece,
        description=description.strip(),
        performed_by=performed_by.strip(),
        performed_on=performed_on,
        cost_minor=cost_minor,
    )
    return save_restoration(restoration, by=by)


@transaction.atomic
def save_restoration(restoration: Restoration, *, by: User) -> Restoration:
    """Add a restoration, or save a staff correction to one."""
    before = None
    if not restoration._state.adding:
        before = audit.snapshot(Restoration.objects.get(pk=restoration.pk))
    restoration.full_clean()
    restoration.save()
    audit.record_saved(restoration, before=before, by=by)
    return restoration
