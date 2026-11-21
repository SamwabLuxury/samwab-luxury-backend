"""Write audit events. Other apps call these from their own services, inside the
same transaction as the change, so a change and its event are saved together or
not at all.

The usual pattern in a service::

    before = audit.snapshot(entry)          # skip for a new row
    ...make and save the change...
    audit.record_saved(entry, before=before, by=staff)

``record`` is for actions that are more than a field edit (``activated``,
``custody_moved``); ``record_deleted`` for a row that is gone.
"""

import json
import uuid
from collections.abc import Iterable
from typing import Any

from django.core.serializers.json import DjangoJSONEncoder
from django.db import models

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.core.client_ip import get_client_ip
from apps.core.request_id import NO_REQUEST_ID, get_request_id

# Columns that never go into ``changes``: the row's own id and clock columns, and
# ``updated_by``, which the event's actor already records.
_NOT_RECORDED = frozenset({"id", "created_at", "updated_at", "updated_by_id"})

Snapshot = dict[str, Any]


def is_recorded_field(attname: str) -> bool:
    """Whether a column's value goes into an audit event. Encrypted columns never do."""
    return attname not in _NOT_RECORDED and not attname.endswith("_enc")


def _plain(value: Any) -> Any:
    """The value as the JSON column will store it, so before and after compare fairly."""
    return json.loads(json.dumps(value, cls=DjangoJSONEncoder))


def snapshot(
    instance: models.Model, *, exclude: Iterable[str] = (), many: Iterable[str] = ()
) -> Snapshot:
    """The row's recorded values: ``{column: value}``. Related rows appear by id.

    ``many`` names many-to-many fields to include as a sorted list of names.
    """
    skipped = set(exclude)
    values: Snapshot = {
        field.attname: _plain(field.value_from_object(instance))
        for field in instance._meta.concrete_fields
        if is_recorded_field(field.attname) and field.name not in skipped
    }
    for name in many:
        values[name] = sorted(str(row) for row in getattr(instance, name).all())
    return values


def difference(before: Snapshot | None, after: Snapshot | None) -> dict[str, Any]:
    """``{field: {"from": old, "to": new}}`` for each field that differs."""
    old, new = before or {}, after or {}
    changes: dict[str, Any] = {}
    for name in [*old, *(key for key in new if key not in old)]:
        if after is None:
            changes[name] = {"from": old[name]}
        elif before is None:
            changes[name] = {"to": new[name]}
        elif old.get(name) != new.get(name):
            changes[name] = {"from": old.get(name), "to": new.get(name)}
    return changes


def _label(model: type[models.Model]) -> str:
    return model._meta.label_lower


def _write(
    verb: str,
    model: type[models.Model],
    object_id: Any,
    *,
    by: User | None,
    changes: dict[str, Any],
) -> AuditEvent:
    if not isinstance(object_id, uuid.UUID):
        raise TypeError(f"Only rows with a UUID id can be audited, not {_label(model)}.")
    request_id = get_request_id()
    return AuditEvent.objects.create(
        actor=by,
        action=f"{_label(model)}.{verb}",
        object_type=_label(model),
        object_id=object_id,
        changes=changes,
        ip_address=get_client_ip(),
        request_id=None if request_id == NO_REQUEST_ID else request_id,
    )


def record(
    verb: str, instance: models.Model, *, by: User | None, changes: dict[str, Any] | None = None
) -> AuditEvent:
    """Record ``verb`` (for example ``retired``) for a row."""
    return _write(verb, type(instance), instance.pk, by=by, changes=changes or {})


def record_saved(
    instance: models.Model,
    *,
    before: Snapshot | None,
    by: User | None,
    exclude: Iterable[str] = (),
    many: Iterable[str] = (),
) -> AuditEvent | None:
    """Record ``created`` (no ``before``) or ``changed``. Nothing is written if nothing changed."""
    after = snapshot(instance, exclude=exclude, many=many)
    changes = difference(before, after)
    if before is not None and not changes:
        return None
    return record("created" if before is None else "changed", instance, by=by, changes=changes)


def record_deleted(
    model: type[models.Model], object_id: uuid.UUID, *, before: Snapshot, by: User | None
) -> AuditEvent:
    """Record ``deleted`` with the row's last values."""
    return _write("deleted", model, object_id, by=by, changes=difference(before, None))


def save_inline_rows(formset: Any, *, by: User | None) -> None:
    """Save an admin inline (such as the shots of a protocol), recording every row it touches.

    Call it from ``ModelAdmin.save_formset``; the admin has already checked the forms.
    This is the pattern from Django's admin docs: ``save(commit=False)``, delete the
    rows marked for deletion, save the rest, then ``save_m2m()``.
    """
    rows = formset.save(commit=False)  # new and changed rows, not yet saved
    for row in formset.deleted_objects:
        before, row_id = snapshot(row), row.pk
        row.delete()
        record_deleted(type(row), row_id, before=before, by=by)
    for row in rows:
        stored = None if row._state.adding else type(row)._default_manager.get(pk=row.pk)
        row.save()
        record_saved(row, before=None if stored is None else snapshot(stored), by=by)
    formset.save_m2m()
