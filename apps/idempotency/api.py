"""``@idempotent``: make a create endpoint safe to send twice.

Put it on the view method, under any other decorators::

    class OrderListView(APIView):
        @idempotent
        def post(self, request: Request) -> Response:
            ...

The request must carry an ``Idempotency-Key`` header (the contract requires it on
every request that creates an order, bid, listing, refund or payout). The first
request with a key runs normally. A retry with the same key and the same body
gets the first answer again, with the header ``Idempotent-Replayed: true``, and
nothing runs twice. Login is checked first, as usual.

The decorator also adds the header to the API description.
"""

import functools
import re
from collections.abc import Callable
from typing import Any

from django.db import transaction
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import exceptions
from rest_framework.request import Request
from rest_framework.response import Response

from apps.idempotency import services
from apps.idempotency.exceptions import IdempotencyKeyInvalidError, IdempotencyKeyMissingError

HEADER = "Idempotency-Key"
REPLAYED_HEADER = "Idempotent-Replayed"
# 1 to 255 visible ASCII characters: letters, digits and symbols, no spaces.
_KEY = re.compile(r"[\x21-\x7e]{1,255}")

IDEMPOTENCY_KEY_PARAMETER = OpenApiParameter(
    name=HEADER,
    type={"type": "string", "maxLength": 255},  # a raw schema, as drf-spectacular allows
    location=OpenApiParameter.HEADER,
    required=True,
    description="Repeating a request with the same key returns the first result.",
)


def read_key(request: Request) -> str:
    """The request's key. A quoted key (``"abc"``, the draft standard's form) equals ``abc``."""
    value = request.headers.get(HEADER, "").strip()
    if len(value) >= 2 and value.startswith('"') and value.endswith('"'):
        value = value[1:-1]
    if not value:
        raise IdempotencyKeyMissingError()
    if not _KEY.fullmatch(value):
        raise IdempotencyKeyInvalidError()
    return value


def _plain(data: Any) -> Any:
    """Form data as a plain dict of lists; JSON bodies as they are."""
    return dict(data.lists()) if hasattr(data, "lists") else data


def idempotent[Handler: Callable[..., Response]](handler: Handler) -> Handler:
    @functools.wraps(handler)
    def wrapper(view: Any, request: Request, *args: Any, **kwargs: Any) -> Response:
        if not request.user.is_authenticated:
            raise exceptions.NotAuthenticated()
        key = read_key(request)
        found = services.claim(
            user=request.user,
            key=key,
            endpoint=f"{request.method} {request.path}"[:120],
            request_sha256=services.fingerprint(
                _plain(request.data), query=dict(request.query_params.lists())
            ),
        )
        if found.replay:
            return Response(
                found.row.response_body,
                status=found.row.response_status,
                headers={REPLAYED_HEADER: "true"},
            )
        try:
            with transaction.atomic():
                response = handler(view, request, *args, **kwargs)
                if response.status_code >= 500:
                    transaction.set_rollback(True)
                else:
                    services.complete(found.row, status=response.status_code, body=response.data)
        except BaseException:
            services.release(found.row)
            raise
        if response.status_code >= 500:
            services.release(found.row)
        return response

    return extend_schema(parameters=[IDEMPOTENCY_KEY_PARAMETER])(wrapper)  # type: ignore[return-value]
