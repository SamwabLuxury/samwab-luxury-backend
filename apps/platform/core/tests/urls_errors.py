"""URLs used only by test_errors.py: one small view for each kind of error."""

from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest, HttpResponse
from django.urls import path
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import exceptions, serializers
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.platform.core.exceptions import (
    AppError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
)


class OpenView(APIView):
    """A view anyone may call, so each test reaches the error it wants."""

    authentication_classes = ()
    permission_classes = (AllowAny,)


class LineSerializer(serializers.Serializer[dict[str, object]]):
    price = serializers.IntegerField(min_value=1)


class AddressSerializer(serializers.Serializer[dict[str, object]]):
    city = serializers.CharField()


class OrderSerializer(serializers.Serializer[dict[str, object]]):
    email = serializers.EmailField()
    address = AddressSerializer()
    lines = LineSerializer(many=True)

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        if attrs["email"] == "blocked@example.com":
            raise serializers.ValidationError("This order cannot be placed.", code="blocked")
        return attrs


class ValidateView(OpenView):
    def post(self, request: Request) -> Response:
        OrderSerializer(data=request.data).is_valid(raise_exception=True)
        return Response({"ok": True})


class ManyView(OpenView):
    def post(self, request: Request) -> Response:
        LineSerializer(data=request.data, many=True).is_valid(raise_exception=True)
        return Response({"ok": True})


class PrivateView(APIView):
    """Uses the project defaults, so it needs a logged-in user."""

    def get(self, request: Request) -> Response:
        return Response({"ok": True})


class DrfForbiddenView(OpenView):
    def get(self, request: Request) -> Response:
        raise exceptions.PermissionDenied()


class DjangoForbiddenView(OpenView):
    def get(self, request: Request) -> Response:
        raise PermissionDenied()


class DjangoMissingView(OpenView):
    def get(self, request: Request) -> Response:
        raise Http404()


class ThrottledView(OpenView):
    def get(self, request: Request) -> Response:
        raise exceptions.Throttled(wait=30)


class ConflictView(OpenView):
    def get(self, request: Request) -> Response:
        raise ConflictError()


class AppNotFoundView(OpenView):
    def get(self, request: Request) -> Response:
        raise NotFoundError()


class AppForbiddenView(OpenView):
    def get(self, request: Request) -> Response:
        raise PermissionDeniedError()


class BidTooLowError(AppError):
    code = "bid_too_low"
    message = "The bid is below the lowest amount allowed."


class CustomAppErrorView(OpenView):
    def get(self, request: Request) -> Response:
        raise BidTooLowError()


class CustomMessageView(OpenView):
    def get(self, request: Request) -> Response:
        raise AppError("Pick a later date.", code="date_too_early")


class CrashView(OpenView):
    def get(self, request: Request) -> Response:
        raise RuntimeError("secret-database-password")


def plain_crash(request: HttpRequest) -> HttpResponse:
    raise RuntimeError("secret-database-password")


@ensure_csrf_cookie
def plain_form(request: HttpRequest) -> HttpResponse:
    """A plain Django view, so Django's CSRF check applies (DRF views skip it)."""
    return HttpResponse("ok")


urlpatterns = [
    path("api/v1/validate/", ValidateView.as_view()),
    path("api/v1/many/", ManyView.as_view()),
    path("api/v1/private/", PrivateView.as_view()),
    path("api/v1/drf-forbidden/", DrfForbiddenView.as_view()),
    path("api/v1/django-forbidden/", DjangoForbiddenView.as_view()),
    path("api/v1/django-missing/", DjangoMissingView.as_view()),
    path("api/v1/throttled/", ThrottledView.as_view()),
    path("api/v1/conflict/", ConflictView.as_view()),
    path("api/v1/app-not-found/", AppNotFoundView.as_view()),
    path("api/v1/app-forbidden/", AppForbiddenView.as_view()),
    path("api/v1/custom-app-error/", CustomAppErrorView.as_view()),
    path("api/v1/custom-message/", CustomMessageView.as_view()),
    path("api/v1/crash/", CrashView.as_view()),
    path("pages/crash/", plain_crash),
    path("api/v1/plain-form/", plain_form),
    path("pages/plain-form/", plain_form),
]

# The same handlers the real project uses (configurations/urls.py).
handler404 = "apps.platform.core.api.errors.page_not_found"
handler500 = "apps.platform.core.api.errors.server_error"
