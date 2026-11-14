from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    """Says whether the API process is up.

    Hosts and uptime checkers call this, so it needs no login
    and does not touch the database.
    """

    authentication_classes = ()
    permission_classes = (AllowAny,)

    @extend_schema(
        summary="Check that the API is running",
        responses=inline_serializer("Health", {"status": serializers.CharField()}),
        auth=[],
    )
    def get(self, request: Request) -> Response:
        return Response({"status": "ok"})
