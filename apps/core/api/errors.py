"""One error format for the whole API.

Every error response has the same shape (RFC 9457 "Problem Details"), so the
front end needs only one piece of code to read errors::

    {
      "type": "about:blank",
      "title": "Bad Request",
      "status": 400,
      "code": "validation_error",
      "detail": "One or more fields are invalid.",
      "errors": [{"field": "email", "code": "required", "message": "This field is required."}],
      "request_id": "0193..."
    }

``code`` is stable and safe for the front end to branch on. ``detail`` is for people.
``errors`` appears only when single fields are wrong.
"""

import logging
from http import HTTPStatus
from typing import Any

from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.views import defaults
from rest_framework import exceptions as drf_exceptions
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler
from rest_framework.views import set_rollback

from apps.core.exceptions import AppError
from apps.core.request_id import get_request_id

logger = logging.getLogger(__name__)

PROBLEM_CONTENT_TYPE = "application/problem+json"
API_PREFIX = "/api/"


def problem_body(
    *,
    status: int,
    code: str,
    detail: str,
    errors: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the body every error response uses."""
    body: dict[str, Any] = {
        "type": "about:blank",
        "title": HTTPStatus(status).phrase,
        "status": status,
        "code": code,
        "detail": detail,
        "request_id": get_request_id(),
    }
    if errors is not None:
        body["errors"] = errors
    return body


def _flatten_field_errors(detail: Any, path: str = "") -> list[dict[str, Any]]:
    """Turn DRF's nested validation errors into one flat list.

    ``{"address": {"city": ["Required."]}}`` becomes one entry with
    ``field`` set to ``"address.city"``. Errors that belong to no single
    field have ``field`` set to ``None``.
    """
    if isinstance(detail, dict):
        found: list[dict[str, Any]] = []
        for key, value in detail.items():
            is_general = key == "non_field_errors"
            child_path = path if is_general else (f"{path}.{key}" if path else str(key))
            found.extend(_flatten_field_errors(value, child_path))
        return found
    if isinstance(detail, list):
        found = []
        for index, item in enumerate(detail):
            is_nested = isinstance(item, dict | list)
            # A list of objects (for example order lines) keeps each object's position.
            child_path = (f"{path}.{index}" if path else str(index)) if is_nested else path
            found.extend(_flatten_field_errors(item, child_path))
        return found
    code = getattr(detail, "code", None) or "invalid"
    return [{"field": path or None, "code": code, "message": str(detail)}]


def exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """DRF calls this for every error raised inside an API view."""
    if isinstance(exc, AppError):
        # Undo any database work the request had started, as DRF does for its own errors.
        set_rollback()
        body = problem_body(status=exc.status_code, code=exc.code, detail=exc.message)
        return Response(body, status=exc.status_code, content_type=PROBLEM_CONTENT_TYPE)

    response = drf_exception_handler(exc, context)
    if response is None:
        # Not an error we know. Django's 500 handling takes over (see server_error below).
        return None

    status = response.status_code
    errors: list[dict[str, Any]] | None = None

    if isinstance(exc, drf_exceptions.ValidationError):
        code = "validation_error"
        detail = "One or more fields are invalid."
        errors = _flatten_field_errors(exc.detail)
    elif isinstance(exc, drf_exceptions.NotAuthenticated | drf_exceptions.AuthenticationFailed):
        # DRF answers 403 here when login is by session cookie. We always answer 401,
        # so the front end can tell "log in first" (401) from "not allowed" (403).
        status = 401
        code = "not_authenticated"
        detail = "You need to log in to do this."
    elif isinstance(exc, drf_exceptions.APIException):
        code = str(exc.get_codes()) if isinstance(exc.detail, str) else exc.default_code
        detail = str(exc.detail)
    elif isinstance(exc, Http404):
        code = "not_found"
        detail = "Not found."
    elif isinstance(exc, PermissionDenied):
        code = "permission_denied"
        detail = "You do not have permission to do this."
    else:  # pragma: no cover - drf_exception_handler only answers for the cases above
        code = "error"
        detail = HTTPStatus(status).phrase

    response.data = problem_body(status=status, code=code, detail=detail, errors=errors)
    response.status_code = status
    response.content_type = PROBLEM_CONTENT_TYPE
    return response


def _is_api_request(request: HttpRequest) -> bool:
    return request.path.startswith(API_PREFIX)


def page_not_found(request: HttpRequest, exception: Exception) -> HttpResponse:
    """Used when no URL matches. API paths get JSON; other paths get Django's page."""
    if _is_api_request(request):
        body = problem_body(status=404, code="not_found", detail="Not found.")
        return JsonResponse(body, status=404, content_type=PROBLEM_CONTENT_TYPE)
    return defaults.page_not_found(request, exception)


def server_error(request: HttpRequest) -> HttpResponse:
    """Used when code crashes. The details go to the logs, never to the caller."""
    if _is_api_request(request):
        body = problem_body(
            status=500,
            code="server_error",
            detail="Something went wrong on our side. Please try again.",
        )
        return JsonResponse(body, status=500, content_type=PROBLEM_CONTENT_TYPE)
    return defaults.server_error(request)
