from typing import Any

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.inventory.catalog.enums import SaleSource
from apps.inventory.pieces.api.serializers import PublicPieceSerializer
from apps.inventory.pieces.enums import AuthenticationBasis, ConditionGrade, VerificationStatus
from apps.platform.core.api.money import MoneySerializer
from apps.shop.listings.enums import AdjustmentDirection
from apps.shop.listings.models import Drop, Listing, ListingPriceAdjustment
from apps.shop.listings.price_explainer import price_explainer


class ListingSerializer(serializers.ModelSerializer[Listing]):
    """A listing as buyers see it. The seller's floor price is never shown."""

    piece = PublicPieceSerializer()
    ask = MoneySerializer()
    reservable = serializers.SerializerMethodField(
        help_text="True when a buyer may reserve it with a deposit. Always false until "
        "reservations are built."
    )
    reserved_until = serializers.SerializerMethodField(
        help_text="Set while another buyer's checkout holds the piece (15 minutes)."
    )
    verification_label = serializers.SerializerMethodField()

    class Meta:
        model = Listing
        fields: tuple[str, ...] = (
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
    def get_reserved_until(self, listing: Listing) -> Any:
        held = getattr(listing, "held_until", None)
        return serializers.DateTimeField().to_representation(held) if held else None

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


class SaleSerializer(serializers.Serializer[Any]):
    sold_on = serializers.DateField()
    price = MoneySerializer()
    source = serializers.ChoiceField(  # type: ignore[assignment]  # a field named like Field.source
        choices=SaleSource.choices, help_text="Where it sold: samwab, auction or marketplace."
    )


class RecentSalesSerializer(serializers.Serializer[Any]):
    grade = serializers.ChoiceField(choices=ConditionGrade.choices, help_text="The piece's grade.")
    days = serializers.IntegerField(help_text="How far back the sales go, such as 365.")
    count = serializers.IntegerField(help_text="How many sales are listed below.")
    low = MoneySerializer()
    high = MoneySerializer()
    median = MoneySerializer()
    sales = SaleSerializer(many=True, help_text="Newest first.")


class PriceAdjustmentSerializer(serializers.ModelSerializer[ListingPriceAdjustment]):
    direction = serializers.ChoiceField(choices=AdjustmentDirection.choices)
    amount = MoneySerializer(help_text="Always positive; `direction` says add or subtract.")

    class Meta:
        model = ListingPriceAdjustment
        fields = ("label", "direction", "amount")


class PriceExplainerSerializer(serializers.Serializer[Any]):
    recent_sales = RecentSalesSerializer(
        allow_null=True,
        help_text="Recent sales of the same design at the same grade. Null when the piece "
        "has no grade or nothing matched: hide the section.",
    )
    adjustments = PriceAdjustmentSerializer(many=True, help_text="Staff lines, in order.")


class ListingDetailSerializer(ListingSerializer):
    """One listing, for its own page: a listing card plus the price explainer."""

    price_explainer = serializers.SerializerMethodField()

    class Meta(ListingSerializer.Meta):
        fields = (*ListingSerializer.Meta.fields, "price_explainer")

    @extend_schema_field(PriceExplainerSerializer)
    def get_price_explainer(self, listing: Listing) -> Any:
        return PriceExplainerSerializer(price_explainer(listing)).data


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


class SavedCardSerializer(ListingSerializer):
    """A saved piece: the shop card plus when it was saved."""

    saved_at = serializers.DateTimeField(read_only=True)

    class Meta(ListingSerializer.Meta):
        fields = (*ListingSerializer.Meta.fields, "saved_at")


class SavedSerializer(serializers.Serializer[Any]):
    """The answer to saving a piece."""

    listing_id = serializers.UUIDField()
    saved_at = serializers.DateTimeField(source="created_at")


class DropSerializer(serializers.ModelSerializer[Any]):
    """A drop as the shop shows it. Times are when it opens to list members
    (``early_access_at``), to everyone (``opens_at``), and when it closes."""

    phase = serializers.SerializerMethodField(
        help_text="upcoming, members (list members only), open, or closed."
    )
    early_access_at = serializers.DateTimeField(source="early_at")
    opens_at = serializers.DateTimeField(source="public_at")
    lot_count = serializers.IntegerField(help_text="How many lots it has, sold or not.")

    class Meta:
        model = Drop
        fields: tuple[str, ...] = (
            "number",
            "name",
            "description",
            "phase",
            "early_access_at",
            "opens_at",
            "closes_at",
            "lot_count",
        )

    @extend_schema_field(serializers.ChoiceField(choices=["upcoming", "members", "open", "closed"]))
    def get_phase(self, drop: Any) -> str:
        return str(drop.phase())


class LotSerializer(ListingSerializer):
    lot_number = serializers.IntegerField(source="drop_lot.lot_number")

    class Meta(ListingSerializer.Meta):
        fields = (*ListingSerializer.Meta.fields, "lot_number")


class DropPageSerializer(DropSerializer):
    you_have_early_access = serializers.SerializerMethodField(
        help_text="True for a logged-in, confirmed mailing-list member."
    )
    lots = serializers.SerializerMethodField(
        help_text="The lots the viewer may see now, in lot order (none for a closed drop)."
    )

    class Meta(DropSerializer.Meta):
        fields = (*DropSerializer.Meta.fields, "you_have_early_access", "lots")

    def get_you_have_early_access(self, drop: Any) -> bool:
        return bool(self.context.get("early_access"))

    @extend_schema_field(LotSerializer(many=True))
    def get_lots(self, drop: Any) -> Any:
        return LotSerializer(self.context["lots"], many=True).data
