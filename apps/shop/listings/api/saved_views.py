"""Save for later: a buyer's own saved pieces. Login is required (the project default)."""

from uuid import UUID

from django.db.models import QuerySet
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.platform.core.api.pagination import ordered_by
from apps.shop.listings import selectors, services
from apps.shop.listings.api.serializers import SavedCardSerializer, SavedSerializer
from apps.shop.listings.models import Listing
from apps.users.accounts.models import User


@extend_schema_view(
    get=extend_schema(
        summary="List my saved pieces",
        description="Pieces I saved that are still for sale, most recently saved first. "
        "Each is a shop card plus `saved_at`. A sold or withdrawn piece drops off.",
        operation_id="saved_list",
        tags=["Listings"],
    )
)
class SavedListView(ListAPIView):  # type: ignore[type-arg]
    serializer_class = SavedCardSerializer
    pagination_class = ordered_by("-saved_at", "-id")

    def get_queryset(self) -> QuerySet[Listing]:
        user: User = self.request.user  # type: ignore[assignment]
        return selectors.saved_listings(user)


class SavedListingView(APIView):
    @extend_schema(
        summary="Save a piece for later",
        description="Saves a piece that is for sale. Saving it again changes nothing and "
        "returns the first `saved_at`. Nothing is held: anyone can still buy it. "
        "404 if it is not for sale; 422 `saved_limit_reached` past 200 pieces.",
        operation_id="saved_put",
        tags=["Listings"],
        request=None,
        responses=SavedSerializer,
    )
    def put(self, request: Request, listing_id: UUID) -> Response:
        user: User = request.user  # type: ignore[assignment]
        saved = services.save_listing(user, listing_id)
        return Response(SavedSerializer(saved).data)

    @extend_schema(
        summary="Remove a saved piece",
        description="Always 204, even if the piece was not saved.",
        operation_id="saved_delete",
        tags=["Listings"],
        responses={204: OpenApiResponse(description="Removed (or was not saved).")},
    )
    def delete(self, request: Request, listing_id: UUID) -> Response:
        user: User = request.user  # type: ignore[assignment]
        services.unsave_listing(user, listing_id)
        return Response(status=status.HTTP_204_NO_CONTENT)
