"""Writes to pieces. Every change to a piece goes through a function here.

Statuses move only through ``move_custody`` and ``set_verification``, which
check the allowed moves in ``state.py`` under a row lock. Later builds call
them: custody events (16), the ledger (17) and authentication checks (28).

Every write records an audit event in the same transaction (build 07).
"""

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Max

from apps.inventory.pieces.models import Media, Piece
from apps.inventory.pieces.photos import PreparedPhoto
from apps.inventory.pieces.state import CUSTODY, VERIFICATION
from apps.platform.audit import services as audit
from apps.platform.core.ids import new_uuid
from apps.platform.core.state_machine import StateMachine
from apps.users.accounts.models import User

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


# ---------- photos ----------


def add_photo(piece: Piece, photo: PreparedPhoto, *, kind: str, by: User) -> Media:
    """Keep a checked photo (from ``photos.prepare``) as the piece's last photo.

    The file is stored under a new random name (the uploader's file name is never
    kept). If saving its row fails, the file is removed again. If an outer
    transaction is cancelled later, the file may stay behind unused: a missing
    file would break a page, an extra one breaks nothing.
    """
    name = default_storage.save(
        f"pieces/{piece.pk}/{new_uuid()}.{photo.extension}", ContentFile(photo.content)
    )
    try:
        with transaction.atomic():
            last = piece.photos.aggregate(last=Max("sort_order"))["last"] or 0
            media = Media.objects.create(
                piece=piece,
                kind=kind,
                file=name,
                sha256=photo.sha256,
                width=photo.width,
                height=photo.height,
                sort_order=last + 1,
            )
            audit.record_saved(media, before=None, by=by)
    except BaseException:
        default_storage.delete(name)
        raise
    return media


@transaction.atomic
def update_photo(media: Media, *, kind: str, sort_order: int, by: User) -> Media:
    """Change a photo's kind or place. The file itself never changes."""
    before = audit.snapshot(Media.objects.get(pk=media.pk))
    media.kind = kind
    media.sort_order = sort_order
    media.full_clean()
    media.save(update_fields=["kind", "sort_order", "updated_at"])
    audit.record_saved(media, before=before, by=by)
    return media


@transaction.atomic
def delete_photo(media: Media, *, by: User) -> None:
    """Delete a photo. Its file is removed only once the deletion is saved."""
    before, media_id, name = audit.snapshot(media), media.pk, media.stored_name
    media.delete()
    audit.record_deleted(Media, media_id, before=before, by=by)
    # robust: if storage is down, the error is logged and the leftover file is harmless.
    transaction.on_commit(lambda: default_storage.delete(name), robust=True)
