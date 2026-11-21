"""Writes to the catalog. Staff make them in the admin site (the catalog manager).

An audit event for every change arrives with build 07. Until then, categories
record who changed them last in ``updated_by``.
"""

from django.db import models, transaction
from django.utils import timezone

from apps.accounts.models import User


def _tracks_editor(model: type[models.Model]) -> bool:
    return any(field.name == "updated_by" for field in model._meta.get_fields())


@transaction.atomic
def save_entry(entry: models.Model, *, by: User) -> None:
    """Check the entry's rules, then save it, recording who changed it where the table can."""
    if _tracks_editor(type(entry)):
        entry.updated_by = by  # type: ignore[attr-defined]
    entry.full_clean()
    entry.save()


@transaction.atomic
def set_active(entries: models.QuerySet[models.Model], *, is_active: bool, by: User) -> int:
    """Retire (``False``) or bring back (``True``) catalog rows. Returns how many changed.

    Nothing is ever deleted: pieces, listings and history keep pointing at retired rows.
    """
    changes: dict[str, object] = {"is_active": is_active, "updated_at": timezone.now()}
    if _tracks_editor(entries.model):
        changes["updated_by"] = by
    return entries.update(**changes)
