"""The public view of a piece, as shown inside a listing.

Serial and date codes, costs, owners and staff notes are never returned.
"""

from typing import Any

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.inventory.catalog.api.serializers import (
    BrandSerializer,
    CategorySerializer,
    ProductModelSerializer,
)
from apps.inventory.pieces.lot_record import Row, lot_record
from apps.inventory.pieces.models import Media, Piece
from apps.platform.core.storage import photo_links


class PhotoSizesSerializer(serializers.Serializer[dict[str, str]]):
    """One link per size; each fits a square of that many pixels and is never enlarged."""

    thumb = serializers.URLField(help_text="Up to 400 px: shop cards and lists.")
    medium = serializers.URLField(help_text="Up to 1,200 px: the piece page.")
    zoom = serializers.URLField(help_text='Up to 2,400 px: the "Look closer" viewer.')


class LotRecordRowSerializer(serializers.Serializer[dict[str, str]]):
    # A field called "label" is fine for DRF; its type stubs mistake it for Field.label.
    label = serializers.CharField()  # type: ignore[assignment]
    value = serializers.CharField()


class MediaSerializer(serializers.ModelSerializer[Media]):
    url = serializers.SerializerMethodField(help_text="Full address of the original photo.")
    sizes = serializers.SerializerMethodField(
        help_text="Smaller copies for faster pages. Use these, not url, in the shop."
    )
    alt = serializers.SerializerMethodField(help_text="Text for screen readers.")
    label = serializers.SerializerMethodField(  # type: ignore[assignment]  # as above
        help_text='What the photo shows, for example "Stamp". Null when staff gave none.'
    )
    caption = serializers.SerializerMethodField(
        help_text="One line on what to look for. Null when staff gave none."
    )

    class Meta:
        model = Media
        fields = ("id", "url", "sizes", "kind", "label", "caption", "alt", "sort_order")

    def get_url(self, media: Media) -> str:
        return self._absolute(media.file.url)

    @extend_schema_field(PhotoSizesSerializer)
    def get_sizes(self, media: Media) -> dict[str, str]:
        return {size: self._absolute(link) for size, link in photo_links(media.stored_name).items()}

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_label(self, media: Media) -> str | None:
        return media.label or None

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_caption(self, media: Media) -> str | None:
        return media.caption or None

    def _absolute(self, link: str) -> str:
        request = self.context.get("request")
        return request.build_absolute_uri(link) if request else link

    def get_alt(self, media: Media) -> str:
        return f"{media.piece.title}, {media.get_kind_display().lower()} {media.sort_order}"


class PublicPieceSerializer(serializers.ModelSerializer[Piece]):
    brand = BrandSerializer()
    category = CategorySerializer()
    product_model = ProductModelSerializer(allow_null=True)
    media = MediaSerializer(source="photos", many=True)
    lot_record = serializers.SerializerMethodField(
        help_text="The piece's facts as rows to show as they are: maker, model, year, size, "
        "grade, then its attributes."
    )

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
            "lot_record",
        )

    @extend_schema_field(LotRecordRowSerializer(many=True))
    def get_lot_record(self, piece: Piece) -> list[Row]:
        return lot_record(piece)

    def to_representation(self, instance: Piece) -> dict[str, Any]:
        # Photos are prefetched with their piece; spare a query per photo for the alt text.
        for media in instance.photos.all():
            media.piece = instance
        return super().to_representation(instance)
