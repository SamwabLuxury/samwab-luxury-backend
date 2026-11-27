"""The flaw list of a condition report: checked once, kept as plain JSON.

Each flaw is ``{"type", "severity", "where", "note", "photo_id"}``:

- ``type``: a code from the category's ``flaw_types`` (any lowercase code when the
  category lists none), such as ``corner_rub``;
- ``severity``: minor, moderate or major;
- ``where``: on the piece, such as "Base, front left" (up to 80 characters);
- ``note``: one sentence for the buyer (up to 300 characters, may be empty);
- ``photo_id``: one of this piece's photos that shows it, or ``None``.

Staff type flaws in the admin one per line: ``type | severity | where | note``.
"""

import re
from collections.abc import Iterable, Mapping
from typing import Any

from django.core.exceptions import ValidationError

from apps.inventory.passports.enums import FlawSeverity
from apps.inventory.pieces.models import Piece

Flaw = dict[str, Any]

_CODE = re.compile(r"[a-z][a-z0-9_]*")
WHERE_MAX, NOTE_MAX = 80, 300


def parse_flaws(text: str) -> list[Flaw]:
    """Turn the admin's lines into flaws (not yet checked against the piece)."""
    flaws = []
    lines = [line.strip() for line in text.replace("\r", "").split("\n")]
    for number, line in enumerate((line for line in lines if line), start=1):
        parts = [part.strip() for part in line.split("|")]
        if len(parts) < 3:
            raise ValidationError(
                f"Line {number}: write what | how bad | where | note (the note may be left out)."
            )
        kind, severity, where, *rest = parts
        flaws.append({"type": kind, "severity": severity, "where": where, "note": " ".join(rest)})
    return flaws


def checked_flaws(piece: Piece, flaws: Iterable[Mapping[str, Any]]) -> list[Flaw]:
    """The flaws in a fixed shape, or ``ValidationError`` naming what is wrong."""
    allowed = set(piece.category.flaw_types or [])
    photos = {str(pk) for pk in piece.photos.values_list("pk", flat=True)}
    result = []
    for number, flaw in enumerate(flaws, start=1):
        kind = str(flaw.get("type", "")).strip()
        severity = str(flaw.get("severity", "")).strip().lower()
        where = str(flaw.get("where", "")).strip()
        note = str(flaw.get("note", "") or "").strip()
        photo = flaw.get("photo_id") or None
        name = f"Flaw {number}"
        if allowed and kind not in allowed:
            raise ValidationError(
                f'{name}: "{kind}" is not a flaw recorded for {piece.category.name}. '
                f"Use one of: {', '.join(sorted(allowed))}."
            )
        if not _CODE.fullmatch(kind):
            raise ValidationError(f"{name}: use a lowercase code such as corner_rub.")
        if severity not in FlawSeverity.values:
            raise ValidationError(f"{name}: say minor, moderate or major.")
        if not where or len(where) > WHERE_MAX:
            raise ValidationError(f"{name}: say where it is, in up to {WHERE_MAX} characters.")
        if len(note) > NOTE_MAX:
            raise ValidationError(f"{name}: keep the note to {NOTE_MAX} characters.")
        if photo is not None and str(photo) not in photos:
            raise ValidationError(f"{name}: choose one of this piece's own photos.")
        result.append(
            {
                "type": kind,
                "severity": severity,
                "where": where,
                "note": note,
                "photo_id": str(photo) if photo else None,
            }
        )
    return result
