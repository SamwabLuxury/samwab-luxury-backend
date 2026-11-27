"""The public passport page. Owners appear by first name and initial; costs, serial
codes and staff names never appear."""

from typing import Any

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.inventory.catalog.enums import ConditionGrade
from apps.inventory.passports.enums import FlawSeverity
from apps.inventory.passports.models import ConditionReport, Passport, Restoration
from apps.inventory.passports.selectors import owner_display
from apps.inventory.pieces.api.serializers import MediaSerializer, PublicPieceSerializer
from apps.inventory.pieces.models import Media


class FlawSerializer(serializers.Serializer[dict[str, Any]]):
    type = serializers.CharField(help_text="A flaw code, such as corner_rub.")
    severity = serializers.ChoiceField(choices=FlawSeverity.choices)
    where = serializers.CharField(help_text="Where on the piece, such as Base, front left.")
    note = serializers.CharField(help_text="One sentence for the buyer; may be empty.")
    photo = MediaSerializer(allow_null=True, help_text="The photo that shows it, if any.")


class ConditionReportSerializer(serializers.ModelSerializer[ConditionReport]):
    grade = serializers.ChoiceField(choices=ConditionGrade.choices)
    flaws = serializers.SerializerMethodField()
    at = serializers.DateTimeField(source="created_at")

    class Meta:
        model = ConditionReport
        fields = ("grade", "summary", "flaws", "at")

    @extend_schema_field(FlawSerializer(many=True))
    def get_flaws(self, report: ConditionReport) -> list[dict[str, Any]]:
        photos: dict[str, Media] = {str(m.pk): m for m in report.piece.photos.all()}
        rows = []
        for flaw in report.flaws:
            photo = photos.get(flaw.get("photo_id") or "")
            shown = MediaSerializer(photo, context=self.context).data if photo else None
            rows.append(
                {**{k: flaw[k] for k in ("type", "severity", "where", "note")}, "photo": shown}
            )
        return rows


class RestorationSerializer(serializers.ModelSerializer[Restoration]):
    class Meta:
        model = Restoration
        fields = ("description", "performed_by", "performed_on")


class OwnershipEntrySerializer(serializers.Serializer[dict[str, Any]]):
    """Filled by the ownership record (build 17)."""

    sequence = serializers.IntegerField()
    reason = serializers.CharField()
    at = serializers.DateTimeField()
    entry_hash = serializers.CharField()


class CertificateSerializer(serializers.Serializer[dict[str, Any]]):
    """Filled by certificates (build 29)."""

    number = serializers.CharField()
    issued_at = serializers.DateTimeField()
    url = serializers.URLField()


class PassportSerializer(serializers.ModelSerializer[Passport]):
    printed_number = serializers.CharField(help_text='As on the card, such as "0042 17".')
    issued_at = serializers.DateTimeField(source="created_at")
    piece = PublicPieceSerializer()
    owner_display = serializers.SerializerMethodField(
        help_text='"Samwab" for house stock, else first name and initial, or "Private owner".'
    )
    ownership_history = serializers.SerializerMethodField(
        help_text="Empty until the ownership record is built."
    )
    condition_reports = ConditionReportSerializer(
        source="piece.condition_reports", many=True, help_text="Newest first."
    )
    restorations = RestorationSerializer(source="piece.restorations", many=True)
    certificates = serializers.SerializerMethodField(
        help_text="Empty until certificates are built."
    )

    class Meta:
        model = Passport
        fields = (
            "passport_number",
            "printed_number",
            "public_code",
            "issued_at",
            "piece",
            "owner_display",
            "ownership_history",
            "condition_reports",
            "restorations",
            "certificates",
        )

    def get_owner_display(self, passport: Passport) -> str:
        return owner_display(passport.piece)

    @extend_schema_field(OwnershipEntrySerializer(many=True))
    def get_ownership_history(self, passport: Passport) -> list[dict[str, Any]]:
        return []

    @extend_schema_field(CertificateSerializer(many=True))
    def get_certificates(self, passport: Passport) -> list[dict[str, Any]]:
        return []
