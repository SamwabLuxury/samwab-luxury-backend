"""A small create endpoint used only by the idempotency tests.

No real endpoint needs an Idempotency-Key yet (listings, bids and orders come in
later builds), so the tests drive the decorator through this one.
"""

from typing import Any

from django.urls import path
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import Material
from apps.core.exceptions import AppError
from apps.idempotency.api import idempotent


class TooExpensive(AppError):
    code = "too_expensive"
    message = "That costs too much."


class CreateMaterialView(APIView):
    """Creates a material, so a test can count how many times the work really ran."""

    @idempotent
    def post(self, request: Request) -> Response:
        data: dict[str, Any] = request.data  # type: ignore[assignment]
        name = str(data.get("name", ""))
        if name == "refuse":
            raise TooExpensive()
        if name == "server-error":
            return Response({"detail": "broken"}, status=503)
        material = Material.objects.create(name=name)
        return Response({"id": str(material.id), "name": material.name}, status=201)

    def get(self, request: Request, *args: Any) -> Response:
        return Response({"count": Material.objects.count()})


class OpenView(APIView):
    """Anyone may call it, but keys belong to a person, so the decorator still needs a login."""

    permission_classes = (AllowAny,)

    @idempotent
    def post(self, request: Request) -> Response:
        return Response(status=201)  # pragma: no cover - never reached without a login


urlpatterns = [
    path("api/v1/test-materials/", CreateMaterialView.as_view()),
    path("api/v1/test-open/", OpenView.as_view()),
]
