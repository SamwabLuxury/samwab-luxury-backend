"""Sign-up, email codes, login, logout and password reset, through allauth's API.

These run the real HTTP flow the web app uses, at /_allauth/browser/v1/.
allauth answers in its own format: {"status", "data", "meta"} or {"status", "errors"}.
"""

import pytest
from django.core import mail
from django.core.cache import cache
from django.test import Client, override_settings

from apps.users.accounts.models import User
from apps.users.accounts.tests.helpers import (
    PASSWORD,
    error_codes,
    last_code,
    pending_flows,
    post,
    sign_up,
    sign_up_and_verify,
    verify,
)

pytestmark = pytest.mark.django_db

ME_URL = "/api/v1/me/"


# ---------- sign-up ----------


def test_sign_up_creates_one_account_and_asks_for_the_email_code(client: Client) -> None:
    response = sign_up(client)

    assert response.status_code == 401
    assert pending_flows(response) == ["verify_email"]
    assert response.json()["meta"]["is_authenticated"] is False
    assert User.objects.count() == 1
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["ada@example.com"]
    assert mail.outbox[0].subject.startswith("Samwab: ")
    assert "Samwab Luxury" in mail.outbox[0].body


def test_the_code_is_six_digits(client: Client) -> None:
    sign_up(client)

    code = last_code()

    assert len(code) == 6
    assert code.isdigit()


def test_the_password_reset_code_is_six_digits(client: Client) -> None:
    sign_up_and_verify(client)
    client.logout()
    mail.outbox.clear()

    post(client, "/password/request", {"email": "ada@example.com"})
    code = last_code()

    assert len(code) == 6
    assert code.isdigit()


def test_codes_use_allauths_documented_setting() -> None:
    """One documented setting shapes every code, so a renamed allauth setting cannot break it."""
    from allauth.account import app_settings

    six_digits = {"numeric": True, "length": 6, "dashed": False}

    assert six_digits == app_settings.EMAIL_VERIFICATION_BY_CODE_FORMAT
    assert six_digits == app_settings.PASSWORD_RESET_BY_CODE_FORMAT


def test_not_logged_in_until_the_email_is_confirmed(client: Client) -> None:
    sign_up(client)

    assert client.get(ME_URL).status_code == 401


@pytest.mark.parametrize("intent", ["buyer", "owner", "dealer"])
def test_the_sign_up_page_used_is_recorded(client: Client, intent: str) -> None:
    sign_up(client, intent=intent)

    assert User.objects.get().signup_intent == intent


@pytest.mark.parametrize("missing", [{}, {"intent": ""}, {"intent": None}])
def test_intent_defaults_to_buyer(client: Client, missing: dict[str, object]) -> None:
    post(client, "/signup", {"email": "ada@example.com", "password": PASSWORD, **missing})

    assert User.objects.get().signup_intent == "buyer"


@pytest.mark.parametrize("bad_intent", ["admin", "owner ", "OWNER", "seller", 3])
def test_an_unknown_intent_is_refused_and_creates_nothing(
    client: Client, bad_intent: object
) -> None:
    response = sign_up(client, intent=bad_intent)

    assert response.status_code == 400
    assert error_codes(response) == [("intent", "invalid_choice")]
    assert User.objects.count() == 0
    assert mail.outbox == []


def test_sign_up_never_grants_a_role(client: Client) -> None:
    sign_up_and_verify(client, intent="dealer")

    user = User.objects.get()
    assert list(user.groups.all()) == []
    assert user.is_staff is False


def test_email_is_stored_in_lowercase(client: Client) -> None:
    sign_up(client, email="  Ada.Obi@Example.COM ")

    assert User.objects.get().email == "ada.obi@example.com"


@pytest.mark.parametrize("bad_email", ["", "not-an-email", "ada@", "@example.com"])
def test_a_bad_email_is_refused(client: Client, bad_email: str) -> None:
    response = sign_up(client, email=bad_email)

    assert response.status_code == 400
    assert "email" in {param for param, _ in error_codes(response)}
    assert User.objects.count() == 0


@pytest.mark.parametrize(
    ("password", "code"),
    [
        ("short1", "password_too_short"),
        ("password", "password_too_common"),
        ("83920174", "password_entirely_numeric"),
        ("ada@example.com", "password_too_similar"),
    ],
)
def test_a_weak_password_is_refused(client: Client, password: str, code: str) -> None:
    response = post(client, "/signup", {"email": "ada@example.com", "password": password})

    assert response.status_code == 400
    assert ("password", code) in error_codes(response)
    assert User.objects.count() == 0


def test_a_missing_password_is_refused(client: Client) -> None:
    response = post(client, "/signup", {"email": "ada@example.com"})

    assert response.status_code == 400
    assert User.objects.count() == 0


@override_settings(ACCOUNT_RATE_LIMITS={"confirm_email": None})
def test_signing_up_again_with_a_used_email_reveals_nothing(client: Client) -> None:
    """Same answer as a new sign-up, so nobody can find out who has an account."""
    sign_up(client, email="ada@example.com")
    mail.outbox.clear()

    response = sign_up(Client(), email="ADA@Example.com")

    assert response.status_code == 401
    assert pending_flows(response) == ["verify_email"]
    assert User.objects.count() == 1
    assert len(mail.outbox) == 1
    assert "already exists" in mail.outbox[0].subject.lower()


def test_signing_up_while_logged_in_is_refused(client: Client) -> None:
    sign_up_and_verify(client)

    response = sign_up(client, email="second@example.com")

    assert response.status_code == 409
    assert User.objects.count() == 1


# ---------- the email code ----------


def test_the_right_code_logs_her_in(client: Client) -> None:
    sign_up(client)

    response = verify(client, last_code())

    assert response.status_code == 200
    assert response.json()["meta"]["is_authenticated"] is True
    assert response.json()["data"]["user"]["email"] == "ada@example.com"
    assert client.get(ME_URL).status_code == 200


def test_a_wrong_code_is_refused(client: Client) -> None:
    sign_up(client)
    wrong = "000000" if last_code() != "000000" else "111111"

    response = verify(client, wrong)

    assert response.status_code == 400
    assert error_codes(response) == [("key", "incorrect_code")]
    assert client.get(ME_URL).status_code == 401


def test_too_many_wrong_codes_end_the_attempt(client: Client) -> None:
    sign_up(client)
    right = last_code()
    wrong = "000000" if right != "000000" else "111111"
    for _ in range(3):
        verify(client, wrong)

    response = verify(client, right)

    assert response.status_code != 200
    assert client.get(ME_URL).status_code == 401


def test_a_code_without_a_pending_sign_up_is_refused(client: Client) -> None:
    response = verify(client, "123456")

    assert response.status_code in (400, 409)
    assert client.get(ME_URL).status_code == 401


# ---------- login and logout ----------


def test_login_with_the_right_password(client: Client) -> None:
    sign_up_and_verify(client)
    client.logout()

    response = post(client, "/login", {"email": "ADA@example.com", "password": PASSWORD})

    assert response.status_code == 200
    assert response.json()["meta"]["is_authenticated"] is True


def test_login_with_a_wrong_password(client: Client) -> None:
    sign_up_and_verify(client)
    client.logout()

    response = post(client, "/login", {"email": "ada@example.com", "password": PASSWORD + "x"})

    assert response.status_code == 400
    assert error_codes(response) == [("password", "email_password_mismatch")]


def test_login_with_an_unknown_email_looks_the_same_as_a_wrong_password(client: Client) -> None:
    response = post(client, "/login", {"email": "nobody@example.com", "password": PASSWORD})

    assert response.status_code == 400
    assert error_codes(response) == [("password", "email_password_mismatch")]


def test_login_before_confirming_the_email_asks_for_the_code(client: Client) -> None:
    sign_up(client)
    # Logging in sends a fresh code, and allauth sends at most one code email per
    # address every 10 seconds. A login that soon after sign-up is refused as
    # "too many attempts". Emptying the counter stands in for waiting 10 seconds.
    cache.clear()
    other = Client()

    response = post(other, "/login", {"email": "ada@example.com", "password": PASSWORD})

    assert response.status_code == 401
    assert pending_flows(response) == ["verify_email"]
    assert other.get(ME_URL).status_code == 401


def test_a_blocked_account_cannot_log_in(client: Client) -> None:
    sign_up_and_verify(client)
    client.logout()
    User.objects.update(is_active=False)

    response = post(client, "/login", {"email": "ada@example.com", "password": PASSWORD})

    assert response.json()["meta"]["is_authenticated"] is False
    assert client.get(ME_URL).status_code == 401


def test_logout_ends_the_session(client: Client) -> None:
    sign_up_and_verify(client)

    response = client.delete("/_allauth/browser/v1/auth/session")

    assert response.status_code == 401
    assert response.json()["meta"]["is_authenticated"] is False
    assert client.get(ME_URL).status_code == 401


def test_repeated_wrong_passwords_are_slowed_down(client: Client) -> None:
    """After 5 wrong passwords for one email, login is refused for 5 minutes."""
    sign_up_and_verify(client)
    client.logout()
    codes = [
        error_codes(post(client, "/login", {"email": "ada@example.com", "password": f"w-{n}"}))
        for n in range(6)
    ]

    assert codes[:5] == [[("password", "email_password_mismatch")]] * 5
    assert codes[5] == [(None, "too_many_login_attempts")]


def test_the_right_password_is_refused_while_slowed_down(client: Client) -> None:
    sign_up_and_verify(client)
    client.logout()
    for n in range(5):
        post(client, "/login", {"email": "ada@example.com", "password": f"w-{n}"})

    response = post(client, "/login", {"email": "ada@example.com", "password": PASSWORD})

    assert response.status_code == 400
    assert error_codes(response) == [(None, "too_many_login_attempts")]
    assert client.get(ME_URL).status_code == 401


# ---------- password reset by code ----------


def test_password_reset_by_code(client: Client) -> None:
    sign_up_and_verify(client)
    client.logout()
    mail.outbox.clear()

    request = post(client, "/password/request", {"email": "Ada@Example.com"})
    code = last_code()
    reset = post(client, "/password/reset", {"key": code, "password": "brand-new-pass-7731"})

    assert request.status_code == 401
    assert pending_flows(request) == ["password_reset_by_code"]
    assert reset.status_code in (200, 401)
    user = User.objects.get()
    assert user.check_password("brand-new-pass-7731") is True
    assert user.check_password(PASSWORD) is False
    login = post(client, "/login", {"email": "ada@example.com", "password": "brand-new-pass-7731"})
    assert login.status_code == 200


def test_password_reset_with_a_wrong_code_changes_nothing(client: Client) -> None:
    sign_up_and_verify(client)
    client.logout()
    mail.outbox.clear()
    post(client, "/password/request", {"email": "ada@example.com"})
    wrong = "000000" if last_code() != "000000" else "111111"

    response = post(client, "/password/reset", {"key": wrong, "password": "brand-new-pass-7731"})

    assert response.status_code == 400
    assert User.objects.get().check_password(PASSWORD) is True


def test_password_reset_for_an_unknown_email_reveals_nothing(client: Client) -> None:
    response = post(client, "/password/request", {"email": "nobody@example.com"})

    assert response.status_code == 401
    assert pending_flows(response) == ["password_reset_by_code"]
    assert User.objects.count() == 0


# ---------- the web app's set-up calls ----------


def test_the_config_call_hands_out_the_csrf_cookie(client: Client) -> None:
    response = client.get("/_allauth/browser/v1/config")

    assert response.status_code == 200
    assert "csrftoken" in response.cookies


def test_sign_up_needs_the_csrf_token() -> None:
    client = Client(enforce_csrf_checks=True)

    without = sign_up(client)
    token = client.get("/_allauth/browser/v1/config").cookies["csrftoken"].value
    with_token = client.post(
        "/_allauth/browser/v1/auth/signup",
        data={"email": "ada@example.com", "password": PASSWORD},
        content_type="application/json",
        headers={"X-CSRFToken": token},
    )

    assert without.status_code == 403
    assert without.json()["code"] == "csrf_failed"
    assert with_token.status_code == 401
    assert User.objects.count() == 1


def test_allauths_own_api_description_is_served(client: Client) -> None:
    assert client.get("/_allauth/openapi.json").status_code == 200
