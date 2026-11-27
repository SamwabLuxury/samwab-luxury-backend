from typing import Any

from rest_framework import serializers

from apps.users.legal.enums import ConsentKind, DocumentKind
from apps.users.legal.models import LegalDocument, TermsAcceptance


class LegalDocumentSerializer(serializers.ModelSerializer[LegalDocument]):
    """A text in force, without its words (the list)."""

    title = serializers.CharField(help_text="The kind in words, such as Terms of service.")
    effective_at = serializers.DateTimeField(help_text="In force since.")
    accepted = serializers.SerializerMethodField(
        help_text="Whether you have accepted this version; null when not logged in."
    )

    class Meta:
        model = LegalDocument
        fields: tuple[str, ...] = (
            "kind",
            "title",
            "version",
            "effective_at",
            "body_sha256",
            "accepted",
        )

    def get_accepted(self, document: LegalDocument) -> bool | None:
        accepted: set[Any] | None = self.context.get("accepted")
        return None if accepted is None else document.pk in accepted


class LegalDocumentTextSerializer(LegalDocumentSerializer):
    """A text in force, with its exact words."""

    body = serializers.CharField(
        help_text="The exact words. Paragraphs are separated by a blank line."
    )

    class Meta(LegalDocumentSerializer.Meta):
        fields = (*LegalDocumentSerializer.Meta.fields, "body")


class LegalAcceptanceSerializer(serializers.Serializer[None]):
    """The contract's ``LegalAcceptance``: the text and version she accepts."""

    document_kind = serializers.ChoiceField(choices=DocumentKind.choices)
    version = serializers.CharField(max_length=20)
    signed_name = serializers.CharField(
        max_length=160,
        required=False,
        allow_blank=True,
        help_text="Her typed full name, for texts she signs.",
    )
    order_id = serializers.UUIDField(required=False, help_text="Only for forms signed per order.")


class AcceptanceSerializer(serializers.ModelSerializer[TermsAcceptance]):
    """What was recorded."""

    document_kind = serializers.CharField(source="legal_document.kind")
    version = serializers.CharField(source="legal_document.version")
    signed_name = serializers.SerializerMethodField()
    order_id = serializers.UUIDField(allow_null=True)

    class Meta:
        model = TermsAcceptance
        fields = ("id", "document_kind", "version", "accepted_at", "signed_name", "order_id")

    def get_signed_name(self, acceptance: TermsAcceptance) -> str | None:
        return acceptance.signed_name or None


class ConsentSerializer(serializers.Serializer[dict[str, Any]]):
    kind = serializers.ChoiceField(choices=ConsentKind.choices)
    granted = serializers.BooleanField()
    granted_at = serializers.DateTimeField(allow_null=True)


class ConsentListSerializer(serializers.Serializer[dict[str, Any]]):
    results = ConsentSerializer(many=True)
