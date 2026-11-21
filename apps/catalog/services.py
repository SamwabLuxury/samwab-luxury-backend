"""Writes to the catalog. Staff make them in the admin site (the catalog manager).

Every write goes through a function here, never straight to the model, so the
rules live in one place when the API or a script needs the same write later.

An audit event for every change arrives with build 07. Until then, categories
record who changed them last in ``updated_by``.
"""

from django.db import models, transaction
from django.db.models import Max, QuerySet
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.enums import ProtocolStatus
from apps.catalog.exceptions import (
    ProtocolHasNoShotsError,
    ProtocolNotActiveError,
    ProtocolNotDraftError,
)
from apps.catalog.models import CaptureProtocol, CaptureShot, Category, ProductModel


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
    _scope(current.category, current.product_model).filter(status=ProtocolStatus.ACTIVE).update(
        status=ProtocolStatus.RETIRED, updated_at=timezone.now()
    )
    current.status = ProtocolStatus.ACTIVE
    current.save(update_fields=["status", "updated_at"])
    return current


@transaction.atomic
def retire_protocol(protocol: CaptureProtocol, *, by: User) -> CaptureProtocol:
    """Stop using a protocol. A design without one falls back to its category's default."""
    current = _locked(protocol)
    if current.status != ProtocolStatus.ACTIVE:
        raise ProtocolNotActiveError()
    current.status = ProtocolStatus.RETIRED
    current.save(update_fields=["status", "updated_at"])
    return current


@transaction.atomic
def new_draft_from(protocol: CaptureProtocol, *, by: User) -> CaptureProtocol:
    """Copy a protocol and its shots into the next draft version, ready to be changed."""
    draft = create_protocol(category=protocol.category, product_model=protocol.product_model, by=by)
    CaptureShot.objects.bulk_create(
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
    return draft
