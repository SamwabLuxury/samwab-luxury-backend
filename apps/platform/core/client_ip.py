"""The IP address of the caller, kept for the audit log.

Like the request ID, it lives in a context variable, so a service can read it
with ``get_client_ip()`` without the request being passed down to it.

Only ``REMOTE_ADDR`` is used. Behind a proxy (Render, in production) that is the
proxy's address; which ``X-Forwarded-For`` hop to trust is decided when the app
is deployed (builds 42 and 44). Until then the header is ignored, because anyone
can send it.
"""

import ipaddress
from collections.abc import Callable
from contextvars import ContextVar

from django.http import HttpRequest, HttpResponse

_client_ip: ContextVar[str | None] = ContextVar("client_ip", default=None)


def get_client_ip() -> str | None:
    """The caller's IP address, or ``None`` outside a request or when it is not one address."""
    return _client_ip.get()


def _one_address(value: str) -> str | None:
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None


class ClientIpMiddleware:
    """Remember the caller's IP address while the request is handled."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        token = _client_ip.set(_one_address(request.META.get("REMOTE_ADDR", "")))
        try:
            return self.get_response(request)
        finally:
            _client_ip.reset(token)
