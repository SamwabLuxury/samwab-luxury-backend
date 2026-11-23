"""Tests for GET and PATCH /api/v1/me/: the logged-in user's own account."""

from typing import Any

import pytest
from django.contrib.auth.models import Group
from django.test import Client

from apps.users.accounts.models import User

pytestmark = pytest.mark.django_db

ME_URL = "/api/v1/me/"
PASSWORD = "correct-horse-battery-9"  # noqa: S105
PROBLEM = "application/problem+json"


@pytest.fixture
def ada() -> User:
    return User.objects.create_user(
        "ada@example.com", PASSWORD, first_name="Adaeze", last_name="Obi", country="NG"
    )


@pytest.fixture
def ada_client(client: Client, ada: User) -> Client:
    client.force_login(ada)
    return client


def patch(client: Client, data: Any) -> Any:
    return client.patch(ME_URL, data=data, content_type="application/json")


def field_errors(response: Any) -> set[str]:
    return {error["field"] for error in response.json()["errors"]}


# ---------- reading ----------


def test_not_logged_in_is_a_401_problem(client: Client) -> None:
    response = client.get(ME_URL)

    assert response.status_code == 401
    assert response["Content-Type"] == PROBLEM
    assert response.json()["code"] == "not_authenticated"


def test_shows_exactly_the_contract_fields(ada_client: Client, ada: User) -> None:
    body = ada_client.get(ME_URL).json()

    assert body == {
        "id": str(ada.id),
        "email": "ada@example.com",
        "first_name": "Adaeze",
        "last_name": "Obi",
        "country": "NG",
        "locale": "en",
        "timezone": "UTC",
        "roles": [],
        "signup_intent": "buyer",
        "next_steps": [],
        "verification_tier": 0,
        "mfa_enabled": False,
    }


def test_never_shows_the_password_hash(ada_client: Client, ada: User) -> None:
    page = ada_client.get(ME_URL).content.decode()

    assert ada.password not in page
    assert "password" not in page


def test_always_shows_the_caller_never_anyone_else(ada_client: Client) -> None:
    User.objects.create_user("tunde@example.com", PASSWORD)

    assert ada_client.get(ME_URL).json()["email"] == "ada@example.com"


def test_roles_come_from_groups_in_the_contracts_order(ada_client: Client, ada: User) -> None:
    ada.groups.add(Group.objects.get(name="dealer"), Group.objects.get(name="owner"))

    assert ada_client.get(ME_URL).json()["roles"] == ["owner", "dealer"]


def test_a_group_that_is_not_a_role_is_not_shown(ada_client: Client, ada: User) -> None:
    ada.groups.add(Group.objects.create(name="beta-testers"))

    assert ada_client.get(ME_URL).json()["roles"] == []


@pytest.mark.parametrize(
    ("intent", "steps"),
    [
        ("buyer", []),
        ("owner", ["accept_terms", "identity_check", "payout_account"]),
        ("dealer", ["identity_check", "dealer_application"]),
    ],
)
def test_next_steps_follow_the_sign_up_page(
    ada_client: Client, ada: User, intent: str, steps: list[str]
) -> None:
    User.objects.filter(pk=ada.pk).update(signup_intent=intent)

    assert ada_client.get(ME_URL).json()["next_steps"] == steps


def test_no_steps_once_the_role_is_granted(ada_client: Client, ada: User) -> None:
    User.objects.filter(pk=ada.pk).update(signup_intent="owner")
    ada.groups.add(Group.objects.get(name="owner"))

    assert ada_client.get(ME_URL).json()["next_steps"] == []


# ---------- changing the profile ----------


def test_change_the_profile(ada_client: Client, ada: User) -> None:
    response = patch(
        ada_client,
        {
            "first_name": "Ada",
            "last_name": "Ọláńrewájú",
            "country": "GB",
            "locale": "en-GB",
            "timezone": "Europe/London",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert (body["first_name"], body["last_name"], body["country"]) == ("Ada", "Ọláńrewájú", "GB")
    ada.refresh_from_db()
    assert (ada.locale, ada.timezone) == ("en-GB", "Europe/London")


def test_change_one_field_leaves_the_others(ada_client: Client, ada: User) -> None:
    patch(ada_client, {"timezone": "Africa/Lagos"})

    ada.refresh_from_db()
    assert (ada.first_name, ada.country, ada.timezone) == ("Adaeze", "NG", "Africa/Lagos")


def test_an_empty_change_changes_nothing(ada_client: Client, ada: User) -> None:
    before = ada.updated_at

    response = patch(ada_client, {})

    assert response.status_code == 200
    ada.refresh_from_db()
    assert ada.updated_at == before


def test_country_can_be_cleared(ada_client: Client, ada: User) -> None:
    patch(ada_client, {"country": ""})

    ada.refresh_from_db()
    assert ada.country == ""


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("country", "ng"),
        ("country", "NGA"),
        ("country", "N1"),
        ("timezone", "Lagos"),
        ("timezone", "Mars/Olympus"),
        ("timezone", ""),
        ("locale", "english"),
        ("locale", "EN"),
        ("locale", "en_GB"),
        ("locale", ""),
        ("first_name", "x" * 151),
        ("last_name", "x" * 151),
    ],
)
def test_bad_values_are_refused_and_nothing_changes(
    ada_client: Client, ada: User, field: str, value: str
) -> None:
    response = patch(ada_client, {field: value})

    assert response.status_code == 400
    assert response["Content-Type"] == PROBLEM
    assert response.json()["code"] == "validation_error"
    assert field_errors(response) == {field}
    fresh = User.objects.get(pk=ada.pk)
    assert getattr(fresh, field) == getattr(ada, field)


def test_wrong_types_are_refused(ada_client: Client) -> None:
    response = patch(ada_client, {"first_name": ["Ada"], "country": 12})

    assert response.status_code == 400
    assert field_errors(response) == {"first_name", "country"}


@pytest.mark.parametrize(
    "field_and_value",
    [
        {"email": "new@example.com"},
        {"roles": ["admin"]},
        {"signup_intent": "dealer"},
        {"verification_tier": 3},
        {"mfa_enabled": True},
        {"next_steps": []},
        {"id": "018f0000-0000-7000-8000-000000000000"},
        {"is_staff": True},
        {"password": "x"},
    ],
)
def test_fields_she_may_not_change_are_ignored(
    ada_client: Client, ada: User, field_and_value: dict[str, Any]
) -> None:
    response = patch(ada_client, field_and_value)

    assert response.status_code == 200
    fresh = User.objects.get(pk=ada.pk)
    assert (fresh.email, fresh.signup_intent, fresh.verification_tier) == (
        "ada@example.com",
        "buyer",
        0,
    )
    assert fresh.is_staff is False
    assert fresh.check_password(PASSWORD) is True
    assert list(fresh.groups.all()) == []


def test_not_logged_in_cannot_change_anything(client: Client, ada: User) -> None:
    response = patch(client, {"first_name": "Hacker"})

    assert response.status_code == 401
    ada.refresh_from_db()
    assert ada.first_name == "Adaeze"


def test_body_that_is_not_json_is_refused(ada_client: Client) -> None:
    response = ada_client.patch(ME_URL, data="{oops", content_type="application/json")

    assert response.status_code == 400
    assert response.json()["code"] == "parse_error"


@pytest.mark.parametrize("method", ["post", "put", "delete"])
def test_other_methods_are_not_allowed(ada_client: Client, method: str) -> None:
    response = getattr(ada_client, method)(ME_URL, content_type="application/json")

    assert response.status_code == 405


def test_a_blocked_user_is_logged_out(ada_client: Client, ada: User) -> None:
    User.objects.filter(pk=ada.pk).update(is_active=False)

    assert ada_client.get(ME_URL).status_code == 401


def test_changing_the_profile_needs_the_csrf_token(ada: User) -> None:
    client = Client(enforce_csrf_checks=True)
    client.force_login(ada)

    without = patch(client, {"first_name": "Ada"})
    token = client.get("/_allauth/browser/v1/config").cookies["csrftoken"].value
    with_token = client.patch(
        ME_URL,
        data={"first_name": "Ada"},
        content_type="application/json",
        headers={"X-CSRFToken": token},
    )

    assert without.status_code == 403
    assert without["Content-Type"] == PROBLEM
    assert without.json()["code"] == "csrf_failed"
    assert with_token.status_code == 200
