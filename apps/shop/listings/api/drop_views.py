"""Drops in the shop. Anyone can read them; a logged-in list member also sees the
lots in a drop's early hours."""

from typing import Any

from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import serializers
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.platform.core.api.pagination import ordered_by
from apps.shop.listings import drops, selectors
from apps.shop.listings.api.serializers import DropPageSerializer, DropSerializer
from apps.shop.listings.models import Drop


class DropPhaseSerializer(serializers.Serializer[None]):
    phase = serializers.ChoiceField(
        choices=["closed"],
        required=False,
        help_text="`closed` lists past drops, most recently closed first (for a recap). "
        "Without it: drops not yet closed, soonest first.",
    )


@extend_schema_view(
    get=extend_schema(
        summary="Running and coming drops, or past ones",
        description="Drops that have not closed, soonest first. `phase` says who may "
        "buy now: `upcoming` (nobody yet), `members` (confirmed mailing-list members), "
        "`open` (everyone). With `?phase=closed`: drops that have closed, most recently "
        "closed first, for a recap. Each carries `lot_count` and `sold_count`.",
        operation_id="drops_list",
        tags=["Drops"],
        parameters=[DropPhaseSerializer],
    )
)
class DropListView(ListAPIView):  # type: ignore[type-arg]
    permission_classes = (AllowAny,)
    serializer_class = DropSerializer

    def wants_closed(self) -> bool:
        chosen = DropPhaseSerializer(data=self.request.query_params)
        chosen.is_valid(raise_exception=True)
        return bool(chosen.validated_data.get("phase") == "closed")

    @property
    def paginator(self) -> Any:
        if not hasattr(self, "_paginator"):
            ordering = ("-closes_at", "-id") if self.wants_closed() else ("public_at", "id")
            self._paginator = ordered_by(*ordering)()
        return self._paginator

    def get_queryset(self) -> QuerySet[Drop]:
        return selectors.closed_drops() if self.wants_closed() else selectors.running_drops()


class DropPageView(APIView):
    permission_classes = (AllowAny,)

    @extend_schema(
        summary="A drop's page",
        description="The drop by its number, with the lots the viewer may see now, in "
        "lot order, for sale or sold (`status`, `sold_at`), and `sold_count`. Before "
        "early access, and for anyone not on the list during it, `lots` is empty. A "
        "closed drop is its recap: every lot, marked sold or not (its unsold pieces are "
        "also in the normal shop). Withdrawn lots are left out.",
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
