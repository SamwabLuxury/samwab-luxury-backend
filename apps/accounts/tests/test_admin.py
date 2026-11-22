"""Tests for the user screens in Django's admin site."""

import pytest
from django.test import Client

from apps.accounts.models import User

pytestmark = pytest.mark.django_db

PASSWORD = "correct-horse-battery-staple"  # noqa: S105
LIST_URL = "/admin/accounts/user/"
ADD_URL = "/admin/accounts/user/add/"


@pytest.fixture
def boss() -> User:
    return User.objects.create_superuser("boss@example.com", PASSWORD)


@pytest.fixture
def boss_client(client: Client, boss: User) -> Client:
    client.force_login(boss)
    return client


def test_anonymous_visitor_is_sent_to_the_login_page(client: Client) -> None:
    response = client.get(LIST_URL)

    assert response.status_code == 302
    assert response["Location"].startswith("/admin/login/")


def test_normal_user_cannot_open_the_admin(client: Client) -> None:
    client.force_login(User.objects.create_user("ada@example.com", PASSWORD))

    response = client.get(LIST_URL)

    assert response.status_code == 302
    assert response["Location"].startswith("/admin/login/")


def test_superuser_can_log_in_to_the_admin_with_email_and_password(
    client: Client, boss: User
) -> None:
    response = client.post(
        "/admin/login/?next=/admin/", {"username": "Boss@Example.com", "password": PASSWORD}
    )

    assert response.status_code == 302
    assert response["Location"] == "/admin/"


def test_user_list_opens_and_shows_users(boss_client: Client) -> None:
    User.objects.create_user("ada@example.com", PASSWORD, first_name="Adaeze")

    response = boss_client.get(LIST_URL)

    assert response.status_code == 200
    page = response.content.decode()
    assert "ada@example.com" in page
    assert "boss@example.com" in page


def test_search_finds_a_user_by_email_or_name(boss_client: Client) -> None:
    User.objects.create_user("ada@example.com", PASSWORD, first_name="Adaeze")
    User.objects.create_user("tunde@example.com", PASSWORD, first_name="Tunde")

    page = boss_client.get(LIST_URL, {"q": "adaeze"}).content.decode()

    assert "ada@example.com" in page
    assert "tunde@example.com" not in page


def test_add_page_opens(boss_client: Client) -> None:
    response = boss_client.get(ADD_URL)

    assert response.status_code == 200
    assert 'name="email"' in response.content.decode()
    assert 'name="username"' not in response.content.decode()


def test_staff_can_add_a_user_with_a_password(boss_client: Client) -> None:
    response = boss_client.post(
        ADD_URL,
        {
            "email": "New.Person@Example.com",
            "usable_password": "true",
            "password1": PASSWORD,
            "password2": PASSWORD,
        },
    )

    assert response.status_code == 302
    user = User.objects.get(email="new.person@example.com")
    assert user.check_password(PASSWORD) is True
    assert user.is_staff is False


def test_adding_a_user_with_an_email_already_in_use_is_refused(boss_client: Client) -> None:
    response = boss_client.post(
        ADD_URL,
        {
            "email": "BOSS@example.com",
            "usable_password": "true",
            "password1": PASSWORD,
            "password2": PASSWORD,
        },
    )

    assert response.status_code == 200  # the form is shown again with an error
    assert User.objects.count() == 1


def test_adding_a_user_with_mismatched_passwords_is_refused(boss_client: Client) -> None:
    response = boss_client.post(
        ADD_URL,
        {
            "email": "new@example.com",
            "usable_password": "true",
            "password1": PASSWORD,
            "password2": PASSWORD + "x",
        },
    )

    assert response.status_code == 200
    assert not User.objects.filter(email="new@example.com").exists()


def test_change_page_opens_and_shows_read_only_details(boss_client: Client) -> None:
    user = User.objects.create_user("ada@example.com", PASSWORD)

    response = boss_client.get(f"{LIST_URL}{user.pk}/change/")

    assert response.status_code == 200
    page = response.content.decode()
    assert str(user.pk) in page
    assert PASSWORD not in page
    assert user.password not in page


def test_staff_can_edit_a_users_details(boss_client: Client) -> None:
    user = User.objects.create_user("ada@example.com", PASSWORD)

    response = boss_client.post(
        f"{LIST_URL}{user.pk}/change/",
        {
            "email": "ada@example.com",
            "first_name": "Adaeze",
            "last_name": "Obi",
            "country": "NG",
            "locale": "en",
            "timezone": "Africa/Lagos",
            "is_active": "on",
            "verification_tier": "0",
        },
    )

    assert response.status_code == 302
    user.refresh_from_db()
    assert (user.first_name, user.country, user.timezone) == ("Adaeze", "NG", "Africa/Lagos")
    assert user.check_password(PASSWORD) is True
