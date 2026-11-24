"""Small helpers for the sign-up and login tests."""

import re
from typing import Any

from django.core import mail
from django.test import Client

AUTH = "/_allauth/browser/v1/auth"
PASSWORD = "correct-horse-battery-9"  # noqa: S105


def post(client: Client, path: str, data: dict[str, Any]) -> Any:
    return client.post(f"{AUTH}{path}", data=data, content_type="application/json")


def sign_up(client: Client, email: str = "ada@example.com", **extra: Any) -> Any:
    return post(client, "/signup", {"email": email, "password": PASSWORD, **extra})


def last_code() -> str:
    """The 6-digit code in the most recent email."""
    assert mail.outbox, "No email was sent."
    body = str(mail.outbox[-1].body)
    found = re.search(r"^(\d{6})$", body, re.MULTILINE)
    assert found, body
    return found.group(1)


def verify(client: Client, code: str) -> Any:
    return post(client, "/email/verify", {"key": code})


def sign_up_and_verify(client: Client, email: str = "ada@example.com", **extra: Any) -> Any:
    sign_up(client, email, **extra)
    return verify(client, last_code())


def pending_flows(response: Any) -> list[str]:
    return [flow["id"] for flow in response.json()["data"]["flows"] if flow.get("is_pending")]


def error_codes(response: Any) -> list[tuple[str | None, str]]:
    return [(error.get("param"), error["code"]) for error in response.json()["errors"]]


def make_staff(email: str = "staff@samwab.com", *role_names: str) -> Any:
    """A staff member who can log in to the admin site, holding the given roles.

    ``create_user`` never makes staff (on purpose), so this sets ``is_staff`` after.
    """
    from django.contrib.auth.models import Group

    from apps.users.accounts.models import User

    user = User.objects.create_user(email, PASSWORD)
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    user.groups.add(*Group.objects.filter(name__in=role_names))
    return user


def totp_code(secret: str, at: float | None = None) -> str:
    """The authenticator app's 6-digit code for ``secret`` (RFC 6238, 30-second steps).

    Written here from the RFC rather than borrowed from allauth, so the tests check
    allauth's answer against an independent one.
    """
    import base64
    import hashlib
    import hmac
    import struct
    import time

    counter = int((time.time() if at is None else at) // 30)
    digest = hmac.new(base64.b32decode(secret), struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{number % 1_000_000:06d}"


def turn_on_two_step(user: Any) -> tuple[str, list[str]]:
    """Give ``user`` an authenticator app and recovery codes; return the secret and codes."""
    from apps.users.accounts import two_step

    secret = two_step.new_secret()
    codes = two_step.turn_on(user, secret, totp_code(secret))
    assert codes is not None
    return secret, codes


def admin_login(client: Client, user: Any) -> None:
    """Log a staff member in to the admin with two-step login already passed.

    The admin asks every staff member for a second step (build 06). Tests that are
    about something else use this instead of ``client.force_login``.
    """
    from allauth.mfa.totp.internal.auth import TOTP

    from apps.users.accounts import selectors, two_step

    if not selectors.has_two_step_login(user):
        TOTP.activate(user, two_step.new_secret())  # straight in: no audit event to count
    client.force_login(user)
    session = client.session
    session[two_step.SESSION_PASSED] = str(user.pk)
    session.save()
