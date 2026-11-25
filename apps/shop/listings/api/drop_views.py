"""Drops in the shop. Anyone can read them; a logged-in list member also sees the
lots in a drop's early hours."""

from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.platform.core.api.pagination import ordered_by
from apps.shop.listings import drops, selectors
from apps.shop.listings.api.serializers import DropPageSerializer, DropSerializer
from apps.shop.listings.models import Drop


@extend_schema_view(
    get=extend_schema(
        summary="Running and coming drops",
        description="Drops that have not closed, soonest first. `phase` says who may "
        "buy now: `upcoming` (nobody yet), `members` (confirmed mailing-list members), "
        "`open` (everyone).",
        operation_id="drops_list",
        tags=["Drops"],
    )
)
class DropListView(ListAPIView):  # type: ignore[type-arg]
    permission_classes = (AllowAny,)
    serializer_class = DropSerializer
    pagination_class = ordered_by("public_at", "id")

    def get_queryset(self) -> QuerySet[Drop]:
        return selectors.running_drops()


class DropPageView(APIView):
    permission_classes = (AllowAny,)

    @extend_schema(
        summary="A drop's page",
        description="The drop by its number, with the lots the viewer may see now, in "
        "lot order. Before early access, and for anyone not on the list during it, "
        "`lots` is empty. A closed drop has no lots: its unsold pieces are in the shop.",
        operation_id="drops_get",
        tags=["Drops"],
        responses=DropPageSerializer,
    )
    def get(self, request: Request, number: int) -> Response:
        drop = get_object_or_404(selectors.drops_with_counts(), number=number)
        viewer = request.user if request.user.is_authenticated else None
        context = {
            "early_access": drops.has_early_access(viewer),
            "lots": selectors.drop_lots(drop, viewer),
        }
        return Response(DropPageSerializer(drop, context=context).data)
