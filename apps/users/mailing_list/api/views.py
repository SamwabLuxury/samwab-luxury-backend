"""Join, confirm and leave the mailing list. No login: anyone can join from the footer."""

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.mailing_list import services
from apps.users.mailing_list.api.serializers import (
    JoinAnswerSerializer,
    JoinSerializer,
    MemberSerializer,
    TokenSerializer,
)


class PublicView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)


class JoinView(PublicView):
    @extend_schema(
        summary="Join the mailing list",
        description="Sends a confirmation email; the address is on the list only after "
        "the link in it is opened. Always 202 with the same answer, whatever the "
        "address's state, so it cannot reveal who is on the list. At most one "
        "confirmation every 10 minutes per address.",
        operation_id="mailing_list_join",
        tags=["Mailing list"],
        auth=[],
        request=JoinSerializer,
        responses={202: JoinAnswerSerializer},
    )
    def post(self, request: Request) -> Response:
        data = JoinSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.join(data.validated_data["email"], source=data.validated_data.get("source", ""))
        return Response({"status": "check_your_email"}, status=status.HTTP_202_ACCEPTED)


class ConfirmView(PublicView):
    @extend_schema(
        summary="Confirm from the emailed link",
        description="`token` is the last part of the confirmation link. Works for 7 days; "
        "confirming twice is fine. 400 `invalid_link` if it is bad, expired or the "
        "address has unsubscribed since.",
        operation_id="mailing_list_confirm",
        tags=["Mailing list"],
        auth=[],
        request=TokenSerializer,
        responses=MemberSerializer,
    )
    def post(self, request: Request) -> Response:
        data = TokenSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(MemberSerializer(services.confirm(data.validated_data["token"])).data)


class UnsubscribeView(PublicView):
    @extend_schema(
        summary="Leave the mailing list",
        description="`token` is the last part of the unsubscribe link in any list email. "
        "Works for good; repeating is fine. 400 `invalid_link` if it is bad.",
        operation_id="mailing_list_unsubscribe",
        tags=["Mailing list"],
        auth=[],
        request=TokenSerializer,
        responses=MemberSerializer,
    )
    def post(self, request: Request) -> Response:
        data = TokenSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(MemberSerializer(services.unsubscribe(data.validated_data["token"])).data)
