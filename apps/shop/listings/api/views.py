"""Public browse: live listings and one listing. Anyone can read them, no login."""

from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import AllowAny

from apps.platform.core.api.pagination import ordered_by
from apps.shop.listings import selectors
from apps.shop.listings.api.serializers import (
    ListingDetailSerializer,
    ListingFilterSerializer,
    ListingSerializer,
)
from apps.shop.listings.models import Listing


@extend_schema_view(
    get=extend_schema(
        summary="Browse live listings",
        description="Live listings, newest first, not counting the lots of a drop that "
        "has not closed (they are on the drop's page). Filter with `q` (every word must appear in "
        "the title, brand or design), `brand` and `category` (slugs; a category includes "
        "the ones under it), `condition_min` and `price_max` (cents). "
        "An unknown slug gives an empty list.",
        operation_id="listings_list",
        tags=["Listings"],
        auth=[],
        parameters=[ListingFilterSerializer],
    )
)
class ListingListView(ListAPIView):  # type: ignore[type-arg]
    authentication_classes = ()
    permission_classes = (AllowAny,)
    serializer_class = ListingSerializer
    pagination_class = ordered_by("-published_at", "-id")

    def get_queryset(self) -> QuerySet[Listing]:
        filters = ListingFilterSerializer(data=self.request.query_params)
        filters.is_valid(raise_exception=True)
        return selectors.shop_listings(**filters.chosen())


@extend_schema_view(
    get=extend_schema(
        summary="Get a listing",
        description="One live listing, with its `price_explainer`: recent sales of the same "
        "design at the same grade, and the staff's price adjustments. A drop's lot is "
        "404 until the viewer may see it (list members in its early hours). "
        "Drafts, withdrawn listings and unknown ids are 404.",
        operation_id="listings_get",
        tags=["Listings"],
        auth=[],
    )
)
class ListingDetailView(RetrieveAPIView):  # type: ignore[type-arg]
    # Logged in or not: a list member sees a drop's lots in its early hours.
    permission_classes = (AllowAny,)
    serializer_class = ListingDetailSerializer
    lookup_url_kwarg = "id"

    def get_queryset(self) -> QuerySet[Listing]:
        viewer = self.request.user if self.request.user.is_authenticated else None
        return selectors.visible_listings(viewer).prefetch_related("price_adjustments")
