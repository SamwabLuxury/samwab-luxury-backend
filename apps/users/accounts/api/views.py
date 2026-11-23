from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.accounts import services
from apps.users.accounts.api.serializers import MeSerializer
from apps.users.accounts.models import User


class MeView(APIView):
    """The logged-in user's own account. Login is required (the project default)."""

    @extend_schema(
        summary="Current user",
        description="Her profile, roles and the onboarding steps still waiting. "
        "The web app uses `roles` and `next_steps` to choose which screen to open.",
        responses=MeSerializer,
    )
    def get(self, request: Request) -> Response:
        user: User = request.user  # type: ignore[assignment]
        return Response(MeSerializer(user).data)

    @extend_schema(summary="Update profile", request=MeSerializer, responses=MeSerializer)
    def patch(self, request: Request) -> Response:
        user: User = request.user  # type: ignore[assignment]
        serializer = MeSerializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        services.update_profile(user=user, changes=dict(serializer.validated_data))
        return Response(MeSerializer(user).data)
