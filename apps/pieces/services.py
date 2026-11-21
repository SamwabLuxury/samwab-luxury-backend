"""Writes to pieces. Every change to a piece goes through a function here.

Statuses move only through ``move_custody`` and ``set_verification``, which
check the allowed moves in ``state.py`` under a row lock. Later builds call
them: custody events (16), the ledger (17) and authentication checks (28).
"""

from django.db import transaction

from apps.accounts.models import User
from apps.core.state_machine import StateMachine
from apps.pieces.models import Piece
from apps.pieces.state import CUSTODY, VERIFICATION

# A form never changes these; only the state machine does.
STATUS_FIELDS = ("verification_status", "custody_status")


@transaction.atomic
def register_piece(piece: Piece, *, by: User) -> Piece:
    """Save a new piece after checking every rule. Blank defaults come from the catalog."""
    piece.full_clean()
    piece.save()
    return piece


@transaction.atomic
def update_piece(piece: Piece, *, by: User) -> Piece:
    """Save staff changes to a piece. Its statuses are kept as they are in the database."""
    piece.full_clean()
    fields = [
        field.name
        for field in Piece._meta.concrete_fields
        if not field.primary_key and field.name not in STATUS_FIELDS
    ]
    piece.save(update_fields=fields)
    piece.refresh_from_db(fields=list(STATUS_FIELDS))
    return piece


def _move(piece: Piece, field: str, machine: StateMachine, to: str) -> Piece:
    current = Piece.objects.select_for_update().get(pk=piece.pk)
    machine.check(getattr(current, field), to)
    setattr(current, field, to)
    current.save(update_fields=[field, "updated_at"])
    setattr(piece, field, to)
    return current


@transaction.atomic
def move_custody(piece: Piece, *, to: str, by: User) -> Piece:
    """Move a piece to its next custody status, such as from ``at_intake`` to ``in_vault``."""
    return _move(piece, "custody_status", CUSTODY, to)


@transaction.atomic
def set_verification(piece: Piece, *, to: str, by: User) -> Piece:
    """Record the result of a piece's authentication: ``verified`` or ``not_authentic``."""
    return _move(piece, "verification_status", VERIFICATION, to)
