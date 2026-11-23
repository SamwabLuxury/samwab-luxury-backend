from typing import Any

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.core.api.money import MoneySerializer
from apps.listings.models import Listing
from apps.pieces.api.serializers import PublicPieceSerializer
from apps.pieces.enums import AuthenticationBasis, ConditionGrade, VerificationStatus


class ListingSerializer(serializers.ModelSerializer[Listing]):
    """A listing as buyers see it. The seller's floor price is never shown."""

    piece = PublicPieceSerializer()
    ask = MoneySerializer()
    reservable = serializers.SerializerMethodField(
        help_text="True when a buyer may reserve it with a deposit. Always false until "
        "reservations are built."
    )
    reserved_until = serializers.SerializerMethodField(
        help_text="Set while another buyer holds a reservation. Always null until "
        "reservations are built."
    )
    verification_label = serializers.SerializerMethodField()

    class Meta:
        model = Listing
        fields = (
            "id",
            "piece",
            "fulfilment",
            "ask",
            "status",
            "reservable",
            "reserved_until",
            "verification_label",
            "published_at",
            "expires_at",
        )

    def get_reservable(self, listing: Listing) -> bool:
        return False

    @extend_schema_field(serializers.DateTimeField(allow_null=True))
    def get_reserved_until(self, listing: Listing) -> None:
        return None

    @extend_schema_field(
        serializers.ChoiceField(choices=["verified", "verification_pending", "buyer_authenticates"])
    )
    def get_verification_label(self, listing: Listing) -> str:
        """``verified``, ``buyer_authenticates`` (jewellery the buyer checks) or
        ``verification_pending``."""
        piece = listing.piece
        if piece.verification_status == VerificationStatus.VERIFIED:
            return "verified"
        if piece.authentication_basis == AuthenticationBasis.BUYER_AUTHENTICATED:
            return "buyer_authenticates"
        return "verification_pending"


class ListingFilterSerializer(serializers.Serializer[None]):
    """The query parameters of ``GET /api/v1/listings/``. Empty means no filter."""

    q = serializers.CharField(
        required=False, allow_blank=True, max_length=100, help_text="Words to search for."
    )
    brand = serializers.SlugField(
        required=False, allow_blank=True, max_length=120, help_text="A brand's slug."
    )
    category = serializers.SlugField(
        required=False,
        allow_blank=True,
        max_length=80,
        help_text="A category's slug; includes the categories under it.",
    )
    condition_min = serializers.ChoiceField(
        choices=ConditionGrade.choices,
        required=False,
        help_text="The lowest condition to show.",
    )
    price_max = serializers.IntegerField(
        required=False, min_value=0, help_text="The highest asking price, in cents."
    )

    def chosen(self) -> dict[str, Any]:
        data: dict[str, Any] = self.validated_data
        return {
            "q": data.get("q", ""),
            "brand_slug": data.get("brand", ""),
            "category_slug": data.get("category", ""),
            "condition_min": data.get("condition_min", ""),
            "price_max": data.get("price_max"),
        }
