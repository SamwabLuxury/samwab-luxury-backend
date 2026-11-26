"""A listing offers one piece for sale at an asking price.

The data model's listing also carries consignment details (the fee schedule,
the signed agreement, the early-read check). Those columns arrive with the
builds that create their tables; this build lists **house stock** only, which
needs none of them.

``status`` changes only through ``services`` (see ``state.py``). A piece has at
most one open listing (draft, live or matched) at a time.
"""

from datetime import timedelta
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.inventory.pieces.enums import Source
from apps.inventory.pieces.models import Piece
from apps.platform.core.models import BaseModel
from apps.platform.core.money import DEFAULT_CURRENCY, Money
from apps.shop.listings.enums import (
    OPEN_STATUSES,
    AcquisitionSource,
    AdjustmentDirection,
    Fulfilment,
    ListingStatus,
)


def _known(field: str, choices: type[models.TextChoices], *, blank: bool = False) -> models.Q:
    values = [*choices.values, ""] if blank else choices.values
    return models.Q(**{f"{field}__in": values})


class Listing(BaseModel):
    piece = models.ForeignKey(Piece, on_delete=models.PROTECT, related_name="listings")
    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="listings",
        editable=False,
        help_text="The piece's owner: Samwab's house account for house stock.",
    )
    fulfilment = models.CharField(max_length=20, choices=Fulfilment.choices)
    ask_minor = models.PositiveBigIntegerField(
        "asking price (US cents)", help_text="In cents: $12,500.00 is 1250000."
    )
    floor_minor = models.PositiveBigIntegerField(
        null=True, blank=True, help_text="Consigned pieces only: the owner's agreed minimum."
    )
    currency = models.CharField(max_length=3, default=DEFAULT_CURRENCY, editable=False)
    acquisition_source = models.CharField(
        max_length=30, choices=AcquisitionSource.choices, blank=True
    )
    known_before = models.BooleanField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=ListingStatus.choices, default=ListingStatus.DRAFT, editable=False
    )
    published_at = models.DateTimeField(null=True, blank=True, editable=False)
    expires_at = models.DateTimeField(null=True, blank=True, editable=False)
    sold_at = models.DateTimeField(
        null=True, blank=True, editable=False, help_text="When a paid order sold it (E19)."
    )

    class Meta:
        db_table = "listings"
        ordering = ("-id",)
        verbose_name = "piece for sale"  # what shop staff call it (admin, E16)
        verbose_name_plural = "pieces for sale"
        indexes = (models.Index(fields=("status", "published_at"), name="listings_browse_idx"),)
        constraints = (
            models.CheckConstraint(
                condition=_known("status", ListingStatus), name="listings_status_is_known"
            ),
            models.CheckConstraint(
                condition=_known("fulfilment", Fulfilment), name="listings_fulfilment_is_known"
            ),
            models.CheckConstraint(
                condition=_known("acquisition_source", AcquisitionSource, blank=True),
                name="listings_acquisition_source_is_known",
            ),
            models.CheckConstraint(
                condition=models.Q(ask_minor__gt=0), name="listings_ask_is_positive"
            ),
            models.UniqueConstraint(
                fields=("piece",),
                condition=models.Q(status__in=OPEN_STATUSES),
                name="listings_one_open_per_piece",
                violation_error_message="This piece already has an open listing. "
                "Withdraw it first.",
            ),
        )

    def __str__(self) -> str:
        return f"{self.piece} · {self.ask} · {self.status}"

    @property
    def ask(self) -> Money:
        return Money(self.ask_minor, self.currency)

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_STATUSES

    def clean(self) -> None:
        errors: dict[str, Any] = {}
        if self.piece_id is not None and self.piece.source == Source.CONSIGNED:
            errors["piece"] = (
                "Consigned pieces are listed by their owners (a later build), not by staff."
            )
        if self.floor_minor is not None and (
            self.piece_id is None or self.piece.source == Source.HOUSE_STOCK
        ):
            errors["floor_minor"] = "House stock has no floor price; leave it empty."
        if self.ask_minor is not None and self.ask_minor < 1:
            errors["ask_minor"] = "The asking price must be at least 1 cent."
        if errors:
            raise ValidationError(errors)


class ListingPriceChange(BaseModel):
    """One change of a listing's asking price. Written by ``services.change_ask`` only."""

    listing = models.ForeignKey(Listing, on_delete=models.PROTECT, related_name="price_changes")
    old_ask_minor = models.PositiveBigIntegerField()
    new_ask_minor = models.PositiveBigIntegerField()
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="+"
    )
    changed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "listing_price_changes"
        ordering = ("changed_at", "id")
        verbose_name = "price change"

    def __str__(self) -> str:
        currency = self.listing.currency
        return f"{Money(self.old_ask_minor, currency)} → {Money(self.new_ask_minor, currency)}"


class ListingPriceAdjustment(BaseModel):
    """One line of the price explainer that staff write: "Complete set, +$300".

    Shown in ``sort_order`` under the recent sales. Edited on the listing's admin page
    while the listing is open; every add, change and delete is in the audit log.
    The amount is always positive; ``direction`` says whether it adds or subtracts.
    """

    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name="price_adjustments")
    label = models.CharField(max_length=80, help_text="What it is for, such as Complete set.")
    direction = models.CharField(max_length=10, choices=AdjustmentDirection.choices)
    amount_minor = models.PositiveBigIntegerField(
        verbose_name="amount", help_text="US cents: $300.00 is 30000."
    )
    sort_order = models.PositiveSmallIntegerField(default=0, verbose_name="order")

    class Meta:
        db_table = "listing_price_adjustments"
        ordering = ("sort_order", "id")
        verbose_name = "price adjustment"
        constraints = (
            models.CheckConstraint(
                condition=models.Q(amount_minor__gt=0),
                name="listing_price_adjustments_amount_above_0",
            ),
            models.CheckConstraint(
                condition=_known("direction", AdjustmentDirection),
                name="listing_price_adjustments_direction_is_known",
            ),
        )

    def __str__(self) -> str:
        sign = "+" if self.direction == AdjustmentDirection.ADD else "-"
        return f"{self.label} {sign}{self.amount}"

    @property
    def amount(self) -> Money:
        return Money(
            self.amount_minor, self.listing.currency if self.listing_id else DEFAULT_CURRENCY
        )

    def clean(self) -> None:
        if self.amount_minor is not None and self.amount_minor < 1:
            raise ValidationError({"amount_minor": "The amount must be at least 1 cent."})


class SavedListing(BaseModel):
    """A piece a buyer saved for later. On her account, so it is on every device.

    Saving holds nothing: anyone can still buy the piece. The saved list shows only
    listings still for sale, so a sold or withdrawn piece drops off by itself; the
    row stays until she removes it. ``created_at`` is when she saved it.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="saved_listings"
    )
    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name="saved_by")

    class Meta:
        db_table = "saved_listings"
        ordering = ("-id",)
        verbose_name = "saved listing"
        constraints = (
            models.UniqueConstraint(fields=("user", "listing"), name="saved_listings_once"),
        )

    def __str__(self) -> str:
        return f"{self.user.email} saved {self.listing}"


class Drop(BaseModel):
    """A dated release of a set of pieces (D46, D51 #5). Buy-now: no bidding.

    Phases, read from the clock (``phase()``): ``upcoming`` until ``early_at``;
    ``members`` (confirmed mailing-list members only) until ``public_at``; ``open``
    (everyone) until ``closes_at``; then ``closed``, and unsold lots are in the normal
    shop. ``early_at`` is ``public_at`` minus ``DROP_EARLY_HOURS``.
    """

    number = models.PositiveIntegerField(unique=True, help_text="Drop Nº 7 is 7.")
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, max_length=2000)
    public_at = models.DateTimeField(
        verbose_name="opens to everyone at",
        help_text="List members get in DROP_EARLY_HOURS (24) hours before this.",
    )
    closes_at = models.DateTimeField(help_text="Unsold lots move to the normal shop then.")
    announced_at = models.DateTimeField(
        null=True, blank=True, editable=False, help_text="When the list was emailed."
    )

    class Meta:
        db_table = "drops"
        ordering = ("public_at", "id")
        constraints = (
            models.CheckConstraint(
                condition=models.Q(closes_at__gt=models.F("public_at")),
                name="drops_close_after_they_open",
            ),
        )

    def __str__(self) -> str:
        return f"Drop {self.number}: {self.name}"

    @property
    def early_at(self) -> Any:
        return self.public_at - timedelta(hours=settings.DROP_EARLY_HOURS)

    def phase(self, now: Any = None) -> str:
        now = now or timezone.now()
        if now < self.early_at:
            return "upcoming"
        if now < self.public_at:
            return "members"
        if now < self.closes_at:
            return "open"
        return "closed"

    def clean(self) -> None:
        if self.public_at and self.closes_at and self.closes_at <= self.public_at:
            raise ValidationError({"closes_at": "A drop must close after it opens."})


class DropLot(BaseModel):
    """One listing in a drop, at its lot number. A listing is in at most one drop."""

    drop = models.ForeignKey(Drop, on_delete=models.PROTECT, related_name="lots")
    listing = models.OneToOneField(Listing, on_delete=models.PROTECT, related_name="drop_lot")
    lot_number = models.PositiveSmallIntegerField()

    class Meta:
        db_table = "drop_lots"
        ordering = ("lot_number", "id")
        verbose_name = "lot"
        constraints = (
            models.UniqueConstraint(fields=("drop", "lot_number"), name="drop_lots_number_once"),
        )

    def __str__(self) -> str:
        return f"Drop {self.drop.number}, lot {self.lot_number}: {self.listing}"

    def clean(self) -> None:
        if self.listing_id is not None and not self.listing.is_open:
            raise ValidationError({"listing": "Only a draft or live listing can be a lot."})
