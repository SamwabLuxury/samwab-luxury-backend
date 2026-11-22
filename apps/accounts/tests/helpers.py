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

    from apps.accounts.models import User

    user = User.objects.create_user(email, PASSWORD)
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    user.groups.add(*Group.objects.filter(name__in=role_names))
    return user
