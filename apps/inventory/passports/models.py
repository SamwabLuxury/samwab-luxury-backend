"""Passports, condition reports and restorations (build 15). Tables as in the data model.

A passport is issued when Samwab verifies a piece: a sequential number printed on
the card and a short unguessable code for the QR link. Condition reports and
restorations are the piece's history that the passport shows.

Differences from the data model: ``condition_reports.model_version_id`` waits for the
model builds (28), and ``supporting_documents`` (scans of brand cards and lab reports)
waits for private file storage. ``restorations.currency`` is fixed to USD, as
everywhere (D18).
"""

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.inventory.catalog.enums import ConditionGrade
from apps.inventory.pieces.models import Piece
from apps.platform.core.ids import new_uuid
from apps.platform.core.money import DEFAULT_CURRENCY


class Passport(models.Model):
    id = models.UUIDField(primary_key=True, default=new_uuid, editable=False)
    piece = models.OneToOneField(Piece, on_delete=models.PROTECT, related_name="passport")
    passport_number = models.PositiveIntegerField(unique=True, editable=False)
    public_code = models.CharField(
        max_length=12, unique=True, editable=False, help_text="The code in the QR link."
    )
    is_public = models.BooleanField(
        "shown to the public",
        default=True,
        help_text="Untick to hide the passport page, for example at the owner's request.",
    )
    created_at = models.DateTimeField("issued at", auto_now_add=True)

    class Meta:
        db_table = "passports"
        ordering = ("-passport_number",)
        permissions = (("verify_passport", "Can verify pieces, which issues their passport"),)
        constraints = (
            models.CheckConstraint(
                condition=Q(passport_number__gte=1), name="passports_number_from_1"
            ),
        )

    def __str__(self) -> str:
        return f"Passport Nº {self.printed_number}"

    @property
    def printed_number(self) -> str:
        """As on the card: at least six digits, the last two set apart ("0042 17")."""
        digits = f"{self.passport_number:06d}"
        return f"{digits[:-2]} {digits[-2:]}"


class ConditionReport(models.Model):
    """One look at a piece: its grade, a summary and its flaws. Never edited."""

    id = models.UUIDField(primary_key=True, default=new_uuid, editable=False)
    piece = models.ForeignKey(Piece, on_delete=models.PROTECT, related_name="condition_reports")
    grade = models.CharField(max_length=20, choices=ConditionGrade.choices)
    summary = models.TextField(blank=True)
    flaws = models.JSONField(
        default=list,
        blank=True,
        help_text="Each flaw: type, severity, where, note and the photo that shows it.",
    )
    ai_generated = models.BooleanField(default=False, editable=False)
    graded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        editable=False,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "condition_reports"
        ordering = ("-created_at", "-id")
        constraints = (
            models.CheckConstraint(
                condition=Q(grade__in=ConditionGrade.values),
                name="condition_reports_grade_is_known",
            ),
        )

    def __str__(self) -> str:
        return f"{self.piece}: {self.get_grade_display()}"


class Restoration(models.Model):
    """Work done on a piece, such as new edge paint. What it cost stays with staff."""

    id = models.UUIDField(primary_key=True, default=new_uuid, editable=False)
    piece = models.ForeignKey(Piece, on_delete=models.PROTECT, related_name="restorations")
    description = models.TextField()
    performed_by = models.CharField(max_length=160, blank=True, help_text="Who did the work.")
    cost_minor = models.PositiveBigIntegerField(null=True, blank=True)
    currency = models.CharField(max_length=3, default=DEFAULT_CURRENCY, editable=False)
    performed_on = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "restorations"
        ordering = ("-performed_on", "-created_at")

    def __str__(self) -> str:
        return self.description
