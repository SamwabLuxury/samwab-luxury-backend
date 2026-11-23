"""Capture protocols: the photos and readings staff take of every piece.

A protocol is the default for a category, or belongs to one design (product
model) when that design needs more. Each one is numbered (version 1, 2, ...),
written as a draft, then made active. Once active its shots never change:
the evidence already taken must always match the protocol it was taken under.
To change it, staff make a new draft version (see ``services.new_draft_from``).
"""

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models.functions import Lower

from apps.inventory.catalog.enums import (
    PHOTO_INSTRUMENTS,
    READING_INSTRUMENTS,
    Instrument,
    ProtocolStatus,
    ShotKind,
)
from apps.inventory.catalog.models.catalog import Category, ProductModel
from apps.platform.core.models import BaseModel

shot_code_validator = RegexValidator(
    r"^[a-z][a-z0-9_]*$", "Use lowercase letters, digits and _, such as heat_stamp_micro."
)

FOR_A_DESIGN = models.Q(product_model__isnull=False)
FOR_A_CATEGORY = models.Q(product_model__isnull=True)
IS_ACTIVE = models.Q(status=ProtocolStatus.ACTIVE)


class CaptureProtocol(BaseModel):
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="capture_protocols"
    )
    product_model = models.ForeignKey(
        ProductModel,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="capture_protocols",
        verbose_name="design",
        help_text="Leave empty for the category's default protocol.",
    )
    version = models.PositiveIntegerField(editable=False)
    status = models.CharField(
        max_length=20,
        choices=ProtocolStatus.choices,
        default=ProtocolStatus.DRAFT,
        editable=False,
    )

    class Meta:
        db_table = "capture_protocols"
        ordering = ("category__sort_order", "category__slug", "product_model__slug", "-version")
        constraints = (
            # Postgres treats empty designs as all different, so the two kinds of
            # protocol (category default, one design) each get their own rule.
            models.UniqueConstraint(
                fields=("category", "product_model", "version"),
                condition=FOR_A_DESIGN,
                name="capture_protocols_design_version",
            ),
            models.UniqueConstraint(
                fields=("category", "version"),
                condition=FOR_A_CATEGORY,
                name="capture_protocols_category_version",
            ),
            models.UniqueConstraint(
                fields=("category", "product_model"),
                condition=FOR_A_DESIGN & IS_ACTIVE,
                name="capture_protocols_one_active_per_design",
            ),
            models.UniqueConstraint(
                fields=("category",),
                condition=FOR_A_CATEGORY & IS_ACTIVE,
                name="capture_protocols_one_active_per_category",
            ),
            models.CheckConstraint(
                condition=models.Q(version__gte=1), name="capture_protocols_version_from_1"
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=ProtocolStatus.values),
                name="capture_protocols_status_is_known",
            ),
        )

    def __str__(self) -> str:
        return f"{self.label}, {self.status}"

    @property
    def label(self) -> str:
        """Which protocol this is, without its status: "Bags (default) v2"."""
        scope = str(self.product_model) if self.product_model else f"{self.category} (default)"
        return f"{scope} v{self.version}"

    @property
    def is_draft(self) -> bool:
        return self.status == ProtocolStatus.DRAFT

    def clean(self) -> None:
        if self.product_model is not None and self.product_model.category_id != self.category_id:
            raise ValidationError(
                {"product_model": "This design belongs to another category. Pick that category."}
            )


class CaptureShot(BaseModel):
    """One photo or reading in a protocol, such as a macro photo of the heat stamp."""

    protocol = models.ForeignKey(CaptureProtocol, on_delete=models.CASCADE, related_name="shots")
    code = models.CharField(
        max_length=50,
        validators=[shot_code_validator],
        help_text="Stays the same across versions, so evidence can be compared.",
    )
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=10, choices=ShotKind.choices, default=ShotKind.PHOTO)
    instrument = models.CharField(max_length=20, choices=Instrument.choices)
    magnification = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Such as 10.")
    instructions = models.TextField(blank=True)
    is_required = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(help_text="Shots are taken in this order.")

    class Meta:
        db_table = "capture_shots"
        ordering = ("sort_order", "code")
        constraints = (
            models.UniqueConstraint(
                fields=("protocol", "code"), name="capture_shots_protocol_code"
            ),
            models.CheckConstraint(
                condition=models.Q(code=Lower("code")) & ~models.Q(code=""),
                name="capture_shots_code_is_lowercase",
            ),
            models.CheckConstraint(
                condition=models.Q(kind=ShotKind.PHOTO, instrument__in=PHOTO_INSTRUMENTS)
                | models.Q(kind=ShotKind.READING, instrument__in=READING_INSTRUMENTS),
                name="capture_shots_instrument_fits_kind",
            ),
            models.CheckConstraint(
                condition=models.Q(magnification__isnull=True) | models.Q(magnification__gte=1),
                name="capture_shots_magnification_from_1",
            ),
        )

    def __str__(self) -> str:
        return f"{self.code}: {self.name}"

    def clean(self) -> None:
        errors: dict[str, str] = {}
        if self.protocol_id is not None and not self.protocol.is_draft:
            errors["protocol"] = (
                "Shots change only while the protocol is a draft. Make a new draft."
            )
        allowed = PHOTO_INSTRUMENTS if self.kind == ShotKind.PHOTO else READING_INSTRUMENTS
        if self.instrument and self.instrument not in allowed:
            names = ", ".join(str(instrument.label) for instrument in allowed)
            errors["instrument"] = f"A {self.kind} uses one of: {names}."
        if errors:
            raise ValidationError(errors)
