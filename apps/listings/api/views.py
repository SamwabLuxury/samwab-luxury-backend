"""Public browse: live listings and one listing. Anyone can read them, no login."""

from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import AllowAny

from apps.core.api.pagination import ordered_by
from apps.listings import selectors
from apps.listings.api.serializers import ListingFilterSerializer, ListingSerializer
from apps.listings.models import Listing


@extend_schema_view(
    get=extend_schema(
        summary="Browse live listings",
        description="Live listings, newest first. Filter with `q` (every word must appear in "
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
        return selectors.public_listings(**filters.chosen())


@extend_schema_view(
    get=extend_schema(
        summary="Get a listing",
        description="One live listing. Drafts, withdrawn listings and unknown ids are 404.",
        operation_id="listings_get",
        tags=["Listings"],
        auth=[],
    )
)
class ListingDetailView(RetrieveAPIView):  # type: ignore[type-arg]
    authentication_classes = ()
    permission_classes = (AllowAny,)
    serializer_class = ListingSerializer
    lookup_url_kwarg = "id"

    def get_queryset(self) -> QuerySet[Listing]:
        return selectors.public_listings()
