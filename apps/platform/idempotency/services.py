"""Claim an idempotency key, keep the answer, replay it.

How one request with a key goes (``apps/platform/idempotency/api.py`` drives it):

1. ``claim`` saves the key at once, in its own short transaction, so a second
   request with the same key sees it straight away.
2. The view does its work. In the same transaction, ``complete`` stores the
   answer. So the work and the stored answer are saved together, or neither is.
3. If the work fails, ``release`` deletes the key, so the request can be tried
   again: nothing it did was saved.

A key still marked "running" after ``CLAIM_TIMEOUT`` belongs to a request that
crashed. Because of step 2, its work was never saved, so the key is taken over.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Final

from django.core.serializers.json import DjangoJSONEncoder
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.platform.idempotency.exceptions import (
    IdempotencyKeyInProgressError,
    IdempotencyKeyReusedError,
)
from apps.platform.idempotency.models import IdempotencyKey
from apps.users.accounts.models import User

# How long a key and its answer are kept (Stripe keeps them at least 24 hours too).
KEY_LIFETIME: Final = timedelta(hours=24)
# After this, an unfinished key is treated as left behind by a crashed request.
# Far longer than any request may run (the web server stops requests long before).
CLAIM_TIMEOUT: Final = timedelta(minutes=5)


@dataclass(frozen=True)
class Claim:
    row: IdempotencyKey
    replay: bool  # True: answer with the stored response and do nothing else


def fingerprint(body: Any, *, query: dict[str, list[str]] | None = None) -> str:
    """A SHA-256 of the request, the same however its JSON fields are ordered."""
    text = json.dumps(
        {"body": body, "query": query or {}},
        sort_keys=True,
        separators=(",", ":"),
        cls=DjangoJSONEncoder,
    )
    return hashlib.sha256(text.encode()).hexdigest()


def _start_fresh(row: IdempotencyKey, *, request_sha256: str, endpoint: str, now: datetime) -> bool:
    """Reset a key someone may also be resetting. True if this request won."""
    won = IdempotencyKey.objects.filter(
        pk=row.pk, created_at=row.created_at, expires_at=row.expires_at
    ).update(
        endpoint=endpoint,
        request_sha256=request_sha256,
        response_status=None,
        response_body=None,
        created_at=now,
        expires_at=now + KEY_LIFETIME,
    )
    return won == 1


def claim(*, user: User, key: str, endpoint: str, request_sha256: str) -> Claim:
    """Claim ``key`` for this request, or say how to answer if it was seen before.

    Raises ``IdempotencyKeyReusedError`` (422) when the key was used for another
    request, and ``IdempotencyKeyInProgressError`` (409) while the first request runs.
    """
    now = timezone.now()
    try:
        with transaction.atomic():
            row = IdempotencyKey.objects.create(
                user=user,
                key=key,
                endpoint=endpoint,
                request_sha256=request_sha256,
                created_at=now,
                expires_at=now + KEY_LIFETIME,
            )
        return Claim(row=row, replay=False)
    except IntegrityError:
        row = IdempotencyKey.objects.get(user=user, key=key)

    if row.expires_at <= now:
        # An old key: this is a new request, whatever it holds.
        pass
    elif row.endpoint != endpoint or row.request_sha256 != request_sha256:
        raise IdempotencyKeyReusedError()
    elif row.is_finished:
        return Claim(row=row, replay=True)
    elif row.created_at > now - CLAIM_TIMEOUT:
        raise IdempotencyKeyInProgressError()

    if not _start_fresh(row, request_sha256=request_sha256, endpoint=endpoint, now=now):
        raise IdempotencyKeyInProgressError()  # another request took it over first
    row.refresh_from_db()
    return Claim(row=row, replay=False)


def complete(row: IdempotencyKey, *, status: int, body: Any) -> None:
    """Keep the answer. Call inside the same transaction as the work."""
    row.response_status = status
    row.response_body = body
    row.save(update_fields=["response_status", "response_body"])


def release(row: IdempotencyKey) -> None:
    """Forget the key after the work failed, so the same request can be sent again."""
    IdempotencyKey.objects.filter(pk=row.pk, response_status__isnull=True).delete()


def delete_expired() -> int:
    """Delete keys past their lifetime. Returns how many."""
    deleted, _ = IdempotencyKey.objects.filter(expires_at__lte=timezone.now()).delete()
    return deleted
