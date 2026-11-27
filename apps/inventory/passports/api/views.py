from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.inventory.passports.api.serializers import PassportSerializer
from apps.inventory.passports.selectors import public_passport
from apps.platform.core.exceptions import NotFoundError


class PassportView(APIView):
    # A public page opened from a QR code: no login and no cookies needed.
    authentication_classes = ()
    permission_classes = (AllowAny,)

    @extend_schema(
        summary="Public passport",
        description="The page a passport QR code opens. No login needed. The code is "
        "not case-sensitive. 404 for an unknown code, a hidden passport, or a piece "
        "later found not authentic. `ownership_history` and `certificates` stay empty "
        "until those builds.",
        operation_id="passport_get",
        tags=["Catalog"],
        responses=PassportSerializer,
    )
    def get(self, request: Request, public_code: str) -> Response:
        passport = public_passport(public_code)
        if passport is None:
            raise NotFoundError()
        return Response(PassportSerializer(passport, context={"request": request}).data)
