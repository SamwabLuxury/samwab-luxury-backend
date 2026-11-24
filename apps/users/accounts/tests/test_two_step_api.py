"""Tests for two-step login through the API (allauth headless) and the reset command."""

from io import StringIO

import pytest
from allauth.mfa.models import Authenticator
from django.core.cache import cache
from django.core.management import CommandError, call_command
from django.test import Client

from apps.platform.audit.models import AuditEvent
from apps.users.accounts.models import User
from apps.users.accounts.tests.helpers import (
    PASSWORD,
    pending_flows,
    post,
    sign_up_and_verify,
    totp_code,
    turn_on_two_step,
)

pytestmark = pytest.mark.django_db

ME_URL = "/api/v1/me/"


def test_me_says_whether_two_step_login_is_on(client: Client) -> None:
    ada = User.objects.create_user("ada@example.com", PASSWORD)
    client.force_login(ada)
    assert client.get(ME_URL).json()["mfa_enabled"] is False
    turn_on_two_step(ada)
    assert client.get(ME_URL).json()["mfa_enabled"] is True


def test_api_login_with_two_step_asks_for_the_code_then_logs_in(client: Client) -> None:
    sign_up_and_verify(client)
    ada = User.objects.get(email="ada@example.com")
    secret, _ = turn_on_two_step(ada)
    cache.clear()
    client.logout()

    response = post(client, "/login", {"email": "ada@example.com", "password": PASSWORD})
    assert response.status_code == 401
    assert pending_flows(response) == ["mfa_authenticate"]
    assert client.get(ME_URL).status_code == 401

    response = post(client, "/2fa/authenticate", {"code": totp_code(secret)})
    assert response.status_code == 200
    assert response.json()["meta"]["is_authenticated"] is True
    assert client.get(ME_URL).status_code == 200


def test_api_login_with_a_wrong_second_code_stays_logged_out(client: Client) -> None:
    sign_up_and_verify(client)
    ada = User.objects.get(email="ada@example.com")
    secret, _ = turn_on_two_step(ada)
    client.logout()
    post(client, "/login", {"email": "ada@example.com", "password": PASSWORD})
    wrong = "000000" if totp_code(secret) != "000000" else "111111"
    assert post(client, "/2fa/authenticate", {"code": wrong}).status_code == 400
    assert client.get(ME_URL).status_code == 401


def test_the_api_lists_her_authenticators(client: Client) -> None:
    sign_up_and_verify(client)
    turn_on_two_step(User.objects.get(email="ada@example.com"))
    response = client.get("/_allauth/browser/v1/account/authenticators")
    assert response.status_code == 200
    assert {item["type"] for item in response.json()["data"]} == {"totp", "recovery_codes"}


def test_passkeys_are_not_offered(client: Client) -> None:
    config = client.get("/_allauth/browser/v1/config").json()["data"]["mfa"]
    assert config["supported_types"] == ["totp", "recovery_codes"]


# ---------- python manage.py reset_two_step ----------


def test_the_reset_command_turns_two_step_off(capsys: pytest.CaptureFixture[str]) -> None:
    ada = User.objects.create_user("ada@example.com", PASSWORD)
    turn_on_two_step(ada)
    out = StringIO()
    call_command("reset_two_step", "ADA@example.com", stdout=out)
    assert not Authenticator.objects.filter(user=ada).exists()
    assert "Two-step login is off for ada@example.com" in out.getvalue()
    assert AuditEvent.objects.filter(action="accounts.user.two_step_reset", actor=None).count() == 1


def test_the_reset_command_says_when_there_was_nothing_to_reset() -> None:
    User.objects.create_user("ada@example.com", PASSWORD)
    out = StringIO()
    call_command("reset_two_step", "ada@example.com", stdout=out)
    assert "had no two-step login" in out.getvalue()


def test_the_reset_command_refuses_an_unknown_email() -> None:
    with pytest.raises(CommandError, match=r"^No account with the email nobody@example\.com\.$"):
        call_command("reset_two_step", "nobody@example.com")
