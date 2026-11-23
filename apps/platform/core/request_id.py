"""A short ID for each request, so one request can be followed through the logs.

The ID is kept in a context variable. Any code that runs while the request is
being handled can read it with ``get_request_id()`` without it being passed around.
"""

import re
from collections.abc import Callable
from contextvars import ContextVar

from django.http import HttpRequest, HttpResponse

from apps.platform.core.ids import new_uuid

REQUEST_ID_HEADER = "X-Request-ID"
NO_REQUEST_ID = "-"

# We accept a caller's ID only if it is short and made of safe characters,
# so nobody can write odd text into our logs.
_SAFE_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{8,64}")

_request_id: ContextVar[str] = ContextVar("request_id", default=NO_REQUEST_ID)


def get_request_id() -> str:
    """The ID of the request being handled, or ``-`` outside a request."""
    return _request_id.get()


class RequestIdMiddleware:
    """Give every request an ID and send it back in the ``X-Request-ID`` header."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        request_id = incoming if _SAFE_REQUEST_ID.fullmatch(incoming) else new_uuid().hex

        # Also kept on the request itself. Django writes some of its own log lines
        # after this middleware has finished, and the log filter reads the ID from here.
        request.request_id = request_id  # type: ignore[attr-defined]

        token = _request_id.set(request_id)
        try:
            response = self.get_response(request)
        finally:
            _request_id.reset(token)

        response[REQUEST_ID_HEADER] = request_id
        return response
