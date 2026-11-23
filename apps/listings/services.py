"""Writes to listings. Every change to a listing goes through a function here.

Statuses move only as ``state.py`` allows, under a row lock, so two staff
members acting at once cannot both publish or withdraw. Every write records an
audit event in the same transaction.
"""

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.audit import services as audit
from apps.listings.enums import Fulfilment, ListingStatus
from apps.listings.exceptions import (
    ListingClosedError,
    ListingNotReadyError,
    PieceAlreadyListedError,
)
from apps.listings.models import Listing, ListingPriceChange
from apps.listings.state import LISTING
from apps.pieces.enums import CustodyStatus, MediaKind, VerificationStatus


@transaction.atomic
def create_listing(listing: Listing, *, by: User) -> Listing:
    """Save a new draft. The seller is always the piece's current owner."""
    listing.seller = listing.piece.current_owner
    listing.status = ListingStatus.DRAFT
    # The database decides "one open listing per piece", so two staff members
    # drafting at the same moment cannot both succeed.
    listing.full_clean(validate_constraints=False)
    try:
        with transaction.atomic():
            listing.save()
    except IntegrityError as clash:
        raise PieceAlreadyListedError() from clash
    audit.record_saved(listing, before=None, by=by)
    return listing


def _locked(listing: Listing) -> Listing:
    return (
        Listing.objects.select_for_update(of=("self",)).select_related("piece").get(pk=listing.pk)
    )


def missing_before_publishing(listing: Listing) -> list[str]:
    """What still stops this listing going live; empty when it is ready."""
    piece = listing.piece
    missing = []
    if piece.verification_status == VerificationStatus.NOT_AUTHENTIC:
        missing.append("The piece was found not authentic and cannot be sold.")
    if (
        listing.fulfilment == Fulfilment.FROM_VAULT
        and piece.custody_status != CustodyStatus.IN_VAULT
    ):
        missing.append(
            f"The piece is not in the vault (it is {piece.get_custody_status_display().lower()})."
        )
    if not piece.photos.filter(kind=MediaKind.LISTING).exists():
        missing.append("Add at least one listing photo to the piece.")
    return missing


def _move(listing: Listing, to: str, *, verb: str, by: User) -> Listing:
    current = _locked(listing)
    was = current.status
    LISTING.check(was, to)
    if to == ListingStatus.LIVE:
        missing = missing_before_publishing(current)
        if missing:
            raise ListingNotReadyError(" ".join(missing))
        current.published_at = timezone.now()
    current.status = to
    current.save(update_fields=["status", "published_at", "updated_at"])
    audit.record(verb, current, by=by, changes={"status": {"from": was, "to": to}})
    listing.status, listing.published_at = current.status, current.published_at
    return current


@transaction.atomic
def publish_listing(listing: Listing, *, by: User) -> Listing:
    """Put a draft on sale. Refused with every missing step listed (HTTP 422)."""
    return _move(listing, ListingStatus.LIVE, verb="published", by=by)


@transaction.atomic
def withdraw_listing(listing: Listing, *, by: User) -> Listing:
    """Take a draft or live listing off sale. A withdrawn listing stays closed."""
    return _move(listing, ListingStatus.WITHDRAWN, verb="withdrawn", by=by)


@transaction.atomic
def change_ask(listing: Listing, *, ask_minor: int, by: User) -> Listing:
    """Change the asking price of an open listing, keeping the old price in its history."""
    current = _locked(listing)
    if not current.is_open:
        raise ListingClosedError()
    old = current.ask_minor
    if ask_minor == old:
        return current
    before = audit.snapshot(current)
    current.ask_minor = ask_minor
    current.full_clean(validate_constraints=False)
    current.save(update_fields=["ask_minor", "updated_at"])
    ListingPriceChange.objects.create(
        listing=current, old_ask_minor=old, new_ask_minor=ask_minor, changed_by=by
    )
    audit.record_saved(current, before=before, by=by)
    listing.ask_minor = ask_minor
    return current
