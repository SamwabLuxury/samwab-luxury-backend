"""Writes to pieces. Every change to a piece goes through a function here.

Statuses move only through ``move_custody`` and ``set_verification``, which
check the allowed moves in ``state.py`` under a row lock. Later builds call
them: custody events (16), the ledger (17) and authentication checks (28).

Every write records an audit event in the same transaction (build 07).
"""

from django.db import transaction

from apps.accounts.models import User
from apps.audit import services as audit
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
    audit.record_saved(piece, before=None, by=by)
    return piece


@transaction.atomic
def update_piece(piece: Piece, *, by: User) -> Piece:
    """Save staff changes to a piece. Its statuses are kept as they are in the database."""
    before = audit.snapshot(Piece.objects.get(pk=piece.pk))
    piece.full_clean()
    fields = [
        field.name
        for field in Piece._meta.concrete_fields
        if not field.primary_key and field.name not in STATUS_FIELDS
    ]
    piece.save(update_fields=fields)
    piece.refresh_from_db(fields=list(STATUS_FIELDS))
    audit.record_saved(piece, before=before, by=by)
    return piece


def material_names(piece: Piece) -> list[str]:
    """The piece's materials by name, sorted: how its audit events show them."""
    return sorted(piece.materials.values_list("name", flat=True))


def record_materials(piece: Piece, *, before: list[str], by: User) -> None:
    """Record a change to a piece's materials, if there was one. Call after saving them."""
    after = material_names(piece)
    if after != before:
        audit.record(
            "materials_changed", piece, by=by, changes={"materials": {"from": before, "to": after}}
        )


def _move(
    piece: Piece, field: str, machine: StateMachine, to: str, *, verb: str, by: User
) -> Piece:
    current = Piece.objects.select_for_update().get(pk=piece.pk)
    was = getattr(current, field)
    machine.check(was, to)
    setattr(current, field, to)
    current.save(update_fields=[field, "updated_at"])
    setattr(piece, field, to)
    audit.record(verb, current, by=by, changes={field: {"from": was, "to": to}})
    return current


@transaction.atomic
def move_custody(piece: Piece, *, to: str, by: User) -> Piece:
    """Move a piece to its next custody status, such as from ``at_intake`` to ``in_vault``."""
    return _move(piece, "custody_status", CUSTODY, to, verb="custody_moved", by=by)


@transaction.atomic
def set_verification(piece: Piece, *, to: str, by: User) -> Piece:
    """Record the result of a piece's authentication: ``verified`` or ``not_authentic``."""
    return _move(piece, "verification_status", VERIFICATION, to, verb="verification_set", by=by)
