"""A buyer's own delivery addresses. Login is required (the project default)."""

from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.generics import ListCreateAPIView
from rest_framework.request import Request
from rest_framework.response import Response

from apps.users.accounts.models import User
from apps.users.addresses import selectors, services
from apps.users.addresses.api.serializers import AddressSerializer
from apps.users.addresses.models import Address


@extend_schema_view(
    get=extend_schema(
        summary="List my addresses", operation_id="addresses_list", tags=["Accounts"]
    ),
    post=extend_schema(
        summary="Add an address",
        description="The first address becomes the default; sending `is_default: true` "
        "makes the new one the default instead of the old. At most 20 per account "
        "(422 `address_limit_reached`).",
        operation_id="addresses_create",
        tags=["Accounts"],
    ),
)
class AddressListView(ListCreateAPIView):  # type: ignore[type-arg]
    serializer_class = AddressSerializer

    def get_queryset(self) -> QuerySet[Address]:
        user: User = self.request.user  # type: ignore[assignment]
        return selectors.addresses_of(user)

    def create(self, request: Request, *args: object, **kwargs: object) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user: User = request.user  # type: ignore[assignment]
        address = services.add_address(user, **serializer.validated_data)
        return Response(AddressSerializer(address).data, status=status.HTTP_201_CREATED)
