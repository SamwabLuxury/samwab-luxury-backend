"""Legal texts: read the ones in force (no login), accept one, give or take back consents."""

from typing import Any

from django.db.models import QuerySet
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.platform.core.api.pagination import ordered_by
from apps.platform.core.client_ip import get_client_ip
from apps.platform.core.exceptions import NotFoundError
from apps.users.accounts.models import User
from apps.users.legal import selectors, services
from apps.users.legal.api.serializers import (
    AcceptanceSerializer,
    ConsentListSerializer,
    ConsentSerializer,
    LegalAcceptanceSerializer,
    LegalDocumentSerializer,
    LegalDocumentTextSerializer,
)
from apps.users.legal.enums import ConsentKind, DocumentKind
from apps.users.legal.models import Consent, LegalDocument


def _user(request: Request) -> User:
    return request.user  # type: ignore[return-value]


def _accepted(request: Request) -> set[Any] | None:
    """What a logged-in reader has accepted; ``None`` for a visitor."""
    return selectors.accepted_ids(_user(request)) if request.user.is_authenticated else None


@extend_schema_view(
    get=extend_schema(
        summary="Legal texts in force",
        description="One row per text people can read and accept now (terms of service, "
        "privacy policy, returns policy...), without the words. No login needed; when "
        "logged in, `accepted` says whether you accepted that version. A kind with "
        "nothing published is left out, and nothing is asked for it.",
        operation_id="legal_documents_list",
        tags=["Accounts"],
    )
)
class LegalDocumentListView(ListAPIView):  # type: ignore[type-arg]
    # Logged in or not: a logged-in reader also sees what she has accepted.
    permission_classes = (AllowAny,)
    serializer_class = LegalDocumentSerializer
    pagination_class = ordered_by("kind")  # one text in force per kind, so kind is unique

    def get_queryset(self) -> QuerySet[LegalDocument]:
        return selectors.texts_in_force()

    def get_serializer_context(self) -> dict[str, Any]:
        return {**super().get_serializer_context(), "accepted": _accepted(self.request)}


class LegalDocumentView(APIView):
    permission_classes = (AllowAny,)

    @extend_schema(
        summary="One legal text, with its words",
        description="The version in force of one kind, with the exact `body` to show "
        "before she accepts. 404 while that kind has nothing published.",
        operation_id="legal_documents_get",
        tags=["Accounts"],
        responses=LegalDocumentTextSerializer,
    )
    def get(self, request: Request, kind: str) -> Response:
        document = selectors.in_force(kind) if kind in DocumentKind.values else None
        if document is None:
            raise NotFoundError()
        context = {"accepted": _accepted(request)}
        return Response(LegalDocumentTextSerializer(document, context=context).data)


class LegalAcceptanceView(APIView):
    @extend_schema(
        summary="Accept a legal document",
        description="Records the version, time, IP address and browser. Only the version "
        "in force can be accepted: 409 `legal_document_not_current` for an older or "
        "unknown one. Accepting again answers with the first record. 422 "
        "`signed_name_required` for texts signed with a typed name (consignment "
        "agreement, buyer authentication form); the buyer authentication form also "
        "needs `order_id` (422 `order_required`), other texts must not have one (422 "
        "`order_not_needed`).",
        operation_id="legal_accept",
        tags=["Accounts"],
        request=LegalAcceptanceSerializer,
        responses={201: AcceptanceSerializer},
    )
    def post(self, request: Request) -> Response:
        incoming = LegalAcceptanceSerializer(data=request.data)
        incoming.is_valid(raise_exception=True)
        data = incoming.validated_data
        acceptance = services.accept(
            _user(request),
            kind=data["document_kind"],
            version=data["version"],
            signed_name=data.get("signed_name", ""),
            order_id=data.get("order_id"),
            ip_address=get_client_ip(),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )
        return Response(AcceptanceSerializer(acceptance).data, status=status.HTTP_201_CREATED)


def _consent(kind: str, consent: Consent | None) -> dict[str, Any]:
    return {
        "kind": kind,
        "granted": consent is not None,
        "granted_at": consent.granted_at if consent else None,
    }


class ConsentListView(APIView):
    @extend_schema(
        summary="My consents",
        description="Every consent, given or not: `marketing` and `training_images` "
        "(photos used to train our authentication model). Not paged: the list is short.",
        operation_id="consents_list",
        tags=["Accounts"],
        responses=ConsentListSerializer,
    )
    def get(self, request: Request) -> Response:
        rows = selectors.active_consents(_user(request))
        results = [_consent(kind, consent) for kind, consent in rows.items()]
        return Response(ConsentListSerializer({"results": results}).data)


class ConsentView(APIView):
    @staticmethod
    def _kind(kind: str) -> str:
        if kind not in ConsentKind.values:
            raise NotFoundError()
        return kind

    @extend_schema(
        summary="Give a consent",
        description="Recorded under the privacy policy in force. Giving it again changes "
        "nothing and answers with the first time. 409 `privacy_policy_not_published` "
        "until a privacy policy is published.",
        operation_id="consents_put",
        tags=["Accounts"],
        request=None,
        responses=ConsentSerializer,
    )
    def put(self, request: Request, kind: str) -> Response:
        consent = services.grant_consent(_user(request), self._kind(kind))
        return Response(ConsentSerializer(_consent(kind, consent)).data)

    @extend_schema(
        summary="Take back a consent",
        description="Always 204, even if it was not given. The history is kept.",
        operation_id="consents_delete",
        tags=["Accounts"],
        responses={204: OpenApiResponse(description="Taken back (or was not given).")},
    )
    def delete(self, request: Request, kind: str) -> Response:
        services.withdraw_consent(_user(request), self._kind(kind))
        return Response(status=status.HTTP_204_NO_CONTENT)
