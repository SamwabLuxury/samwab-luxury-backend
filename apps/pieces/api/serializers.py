"""The public view of a piece, as shown inside a listing.

Serial and date codes, costs, owners and staff notes are never returned.
"""

from typing import Any

from rest_framework import serializers

from apps.catalog.api.serializers import BrandSerializer, CategorySerializer, ProductModelSerializer
from apps.pieces.models import Media, Piece


class MediaSerializer(serializers.ModelSerializer[Media]):
    url = serializers.SerializerMethodField(help_text="Full address of the photo.")
    alt = serializers.SerializerMethodField(help_text="Text for screen readers.")

    class Meta:
        model = Media
        fields = ("id", "url", "kind", "alt", "sort_order")

    def get_url(self, media: Media) -> str:
        request = self.context.get("request")
        url: str = media.file.url
        return request.build_absolute_uri(url) if request else url

    def get_alt(self, media: Media) -> str:
        return f"{media.piece.title}, {media.get_kind_display().lower()} {media.sort_order}"


class PublicPieceSerializer(serializers.ModelSerializer[Piece]):
    brand = BrandSerializer()
    category = CategorySerializer()
    product_model = ProductModelSerializer(allow_null=True)
    media = MediaSerializer(source="photos", many=True)

    class Meta:
        model = Piece
        fields = (
            "id",
            "title",
            "description",
            "brand",
            "category",
            "product_model",
            "department",
            "size_label",
            "production_year",
            "attributes",
            "condition_grade",
            "verification_status",
            "authentication_basis",
            "custody_status",
            "media",
        )

    def to_representation(self, instance: Piece) -> dict[str, Any]:
        # Photos are prefetched with their piece; spare a query per photo for the alt text.
        for media in instance.photos.all():
            media.piece = instance
        return super().to_representation(instance)
