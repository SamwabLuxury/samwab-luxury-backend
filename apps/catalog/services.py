"""Writes to the catalog. Staff make them in the admin site (the catalog manager).

Every write goes through a function here, never straight to the model, so the
rules live in one place when the API or a script needs the same write later.

Every write also records an audit event in the same transaction (build 07).
Categories also keep who changed them last in ``updated_by``.
"""

from django.db import models, transaction
from django.db.models import Max, QuerySet
from django.utils import timezone

from apps.accounts.models import User
from apps.audit import services as audit
from apps.catalog.enums import ProtocolStatus
from apps.catalog.exceptions import (
    ProtocolHasNoShotsError,
    ProtocolNotActiveError,
    ProtocolNotDraftError,
)
from apps.catalog.models import CaptureProtocol, CaptureShot, Category, ProductModel


def _tracks_editor(model: type[models.Model]) -> bool:
    return any(field.name == "updated_by" for field in model._meta.get_fields())


def _stored(entry: models.Model) -> audit.Snapshot | None:
    """The entry's values as they are in the database now, or ``None`` for a new entry."""
    if entry._state.adding:
        return None
    return audit.snapshot(type(entry)._default_manager.get(pk=entry.pk))


@transaction.atomic
def save_entry(entry: models.Model, *, by: User) -> None:
    """Check the entry's rules, then save it, recording who changed it where the table can."""
    before = _stored(entry)
    if _tracks_editor(type(entry)):
        entry.updated_by = by  # type: ignore[attr-defined]
    entry.full_clean()
    entry.save()
    audit.record_saved(entry, before=before, by=by)


@transaction.atomic
def set_active(entries: models.QuerySet[models.Model], *, is_active: bool, by: User) -> int:
    """Retire (``False``) or bring back (``True``) catalog rows. Returns how many changed.

    Nothing is ever deleted: pieces, listings and history keep pointing at retired rows.
    Rows already in the wanted state are left alone and get no audit event.
    """
    # of=self: lock only these rows. PostgreSQL refuses to lock the optional side of a join,
    # and the admin's list query joins related rows for display.
    to_change = list(entries.exclude(is_active=is_active).select_for_update(of=("self",)))
    changes: dict[str, object] = {"is_active": is_active, "updated_at": timezone.now()}
    if _tracks_editor(entries.model):
        changes["updated_by"] = by
    entries.model._default_manager.filter(pk__in=[row.pk for row in to_change]).update(**changes)
    for row in to_change:
        audit.record(
            "restored" if is_active else "retired",
            row,
            by=by,
            changes={"is_active": {"from": not is_active, "to": is_active}},
        )
    return len(to_change)


@transaction.atomic
def delete_entry(entry: models.Model, *, by: User) -> None:
    """Delete a row that may be deleted (a material typo, a comparable sale, a shot).

    The database still refuses a row others depend on (``ProtectedError``).
    """
    before, entry_id = audit.snapshot(entry), entry.pk
    entry.delete()
    audit.record_deleted(type(entry), entry_id, before=before, by=by)


@transaction.atomic
def delete_entries(entries: QuerySet[models.Model], *, by: User) -> int:
    """Delete several rows, all or none, with one audit event each. Returns how many."""
    rows = list(entries)
    for row in rows:
        delete_entry(row, by=by)
    return len(rows)


# ---------- capture protocols ----------


def _scope(category: Category, product_model: ProductModel | None) -> QuerySet[CaptureProtocol]:
    """Every version of the protocol for one category default, or for one design."""
    return CaptureProtocol.objects.filter(category=category, product_model=product_model)


def _next_version(category: Category, product_model: ProductModel | None) -> int:
    # Lock the category row so two staff creating versions at once get 1 and 2, not 1 and 1.
    Category.objects.select_for_update().filter(pk=category.pk).first()
    latest = _scope(category, product_model).aggregate(latest=Max("version"))["latest"]
    return (latest or 0) + 1


def _locked(protocol: CaptureProtocol) -> CaptureProtocol:
    """Read the protocol again under a row lock, so a stale page never acts on old data."""
    return CaptureProtocol.objects.select_for_update().get(pk=protocol.pk)


@transaction.atomic
def add_protocol(protocol: CaptureProtocol, *, by: User) -> CaptureProtocol:
    """Save a new protocol as a draft, numbered after the latest one for the same scope."""
    protocol.status = ProtocolStatus.DRAFT
    protocol.full_clean(exclude=["version"])
    protocol.version = _next_version(protocol.category, protocol.product_model)
    protocol.save()
    audit.record_saved(protocol, before=None, by=by)
    return protocol


def create_protocol(
    *, category: Category, product_model: ProductModel | None = None, by: User
) -> CaptureProtocol:
    """Start a new draft protocol for a category default, or for one design."""
    return add_protocol(CaptureProtocol(category=category, product_model=product_model), by=by)


@transaction.atomic
def activate_protocol(protocol: CaptureProtocol, *, by: User) -> CaptureProtocol:
    """Put a draft into use. The protocol it replaces, if any, is retired."""
    current = _locked(protocol)
    if not current.is_draft:
        raise ProtocolNotDraftError()
    if not current.shots.filter(is_required=True).exists():
        raise ProtocolHasNoShotsError()
    replaced = list(
        _scope(current.category, current.product_model)
        .filter(status=ProtocolStatus.ACTIVE)
        .select_for_update(of=("self",))  # the default order joins the optional design
    )
    for old in replaced:
        _set_status(old, ProtocolStatus.RETIRED, verb="retired", by=by)
    _set_status(current, ProtocolStatus.ACTIVE, verb="activated", by=by)
    return current


@transaction.atomic
def retire_protocol(protocol: CaptureProtocol, *, by: User) -> CaptureProtocol:
    """Stop using a protocol. A design without one falls back to its category's default."""
    current = _locked(protocol)
    if current.status != ProtocolStatus.ACTIVE:
        raise ProtocolNotActiveError()
    _set_status(current, ProtocolStatus.RETIRED, verb="retired", by=by)
    return current


def _set_status(protocol: CaptureProtocol, status: str, *, verb: str, by: User) -> None:
    changes = {"status": {"from": protocol.status, "to": status}}
    protocol.status = status
    protocol.save(update_fields=["status", "updated_at"])
    audit.record(verb, protocol, by=by, changes=changes)


@transaction.atomic
def delete_protocol(protocol: CaptureProtocol, *, by: User) -> None:
    """Delete a draft protocol and its shots. Protocols that were used stay, as history."""
    current = _locked(protocol)
    if not current.is_draft:
        raise ProtocolNotDraftError()
    delete_entry(current, by=by)


@transaction.atomic
def new_draft_from(protocol: CaptureProtocol, *, by: User) -> CaptureProtocol:
    """Copy a protocol and its shots into the next draft version, ready to be changed."""
    draft = create_protocol(category=protocol.category, product_model=protocol.product_model, by=by)
    shots = CaptureShot.objects.bulk_create(
        CaptureShot(
            protocol=draft,
            code=shot.code,
            name=shot.name,
            kind=shot.kind,
            instrument=shot.instrument,
            magnification=shot.magnification,
            instructions=shot.instructions,
            is_required=shot.is_required,
            sort_order=shot.sort_order,
        )
        for shot in protocol.shots.all()
    )
    audit.record(
        "drafted",
        draft,
        by=by,
        changes={"copied_from": str(protocol.pk), "shots_copied": len(shots)},
    )
    return draft
