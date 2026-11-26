"""Public browse: live listings and one listing. Anyone can read them, no login."""

from typing import Any

from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import serializers
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

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
        "An unknown slug gives an empty list. `count` is how many pieces match the "
        "filters, on every page; `results` is one page of them.",
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
    pagination_class = ordered_by("-published_at", "-id", counted=True)

    def chosen_filters(self) -> dict[str, Any]:
        filters = ListingFilterSerializer(data=self.request.query_params)
        filters.is_valid(raise_exception=True)
        return filters.chosen()

    def get_queryset(self) -> QuerySet[Listing]:
        return selectors.shop_listings(**self.chosen_filters())

    def total_count(self, request: Request) -> int:
        return selectors.shop_count(**self.chosen_filters())


class FacetSerializer(serializers.Serializer[None]):
    slug = serializers.CharField()
    name = serializers.CharField()
    count = serializers.IntegerField()


class ShopFacetsSerializer(serializers.Serializer[None]):
    total = serializers.IntegerField(help_text="Pieces matching every filter given.")
    brands = FacetSerializer(
        many=True,
        help_text="Each house with pieces for sale and how many, with every filter but "
        "`brand`. Sorted by name.",
    )
    categories = FacetSerializer(
        many=True,
        help_text="Each top category with pieces for sale and how many (its sub-categories "
        "included), with every filter but `category`. Sorted by name.",
    )


@extend_schema_view(
    get=extend_schema(
        summary="Shop totals and filter counts",
        description="Counts for the shop's filters: `total` (pieces matching every filter), "
        "and a count per house and per top category. Takes the same filters as "
        "`GET /api/v1/listings/`. A house's count leaves out the `brand` filter, so the "
        '"Find a house" list keeps every house while one is chosen; the same for '
        "categories. Lots of a drop that has not closed are not counted, as in the shop.",
        operation_id="listings_facets",
        tags=["Listings"],
        auth=[],
        parameters=[ListingFilterSerializer],
        responses=ShopFacetsSerializer,
    )
)
class ShopFacetsView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)

    def get(self, request: Request) -> Response:
        filters = ListingFilterSerializer(data=request.query_params)
        filters.is_valid(raise_exception=True)
        return Response(selectors.shop_facets(**filters.chosen()))


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
        return selectors.listing_pages(viewer).prefetch_related("price_adjustments")
