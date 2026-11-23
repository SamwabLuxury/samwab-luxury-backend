"""Tests for apps.users.accounts.managers: creating users and finding them at login."""

from typing import Any

import pytest
from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError

from apps.users.accounts.managers import normalise_email
from apps.users.accounts.models import User

pytestmark = pytest.mark.django_db

PASSWORD = "correct-horse-battery-staple"  # noqa: S105


# ---------- normalise_email ----------


@pytest.mark.parametrize(
    ("typed", "stored"),
    [
        ("ada@example.com", "ada@example.com"),
        ("Ada@Example.COM", "ada@example.com"),
        ("  ada@example.com \n", "ada@example.com"),
        ("ADA.LOVELACE+shop@EXAMPLE.com", "ada.lovelace+shop@example.com"),
    ],
)
def test_normalise_email(typed: str, stored: str) -> None:
    assert normalise_email(typed) == stored


# ---------- create_user ----------


def test_create_user_saves_a_normal_active_user() -> None:
    user = User.objects.create_user("Ada@Example.com", PASSWORD)

    saved = User.objects.get(pk=user.pk)
    assert saved.email == "ada@example.com"
    assert saved.is_active is True
    assert saved.is_staff is False
    assert saved.is_superuser is False
    assert saved.is_house_account is False
    assert saved.verification_tier == 0
    assert saved.country == ""
    assert saved.locale == "en"
    assert saved.timezone == "UTC"
    assert saved.anonymised_at is None
    assert saved.last_login is None


def test_password_is_stored_as_a_hash_never_as_typed() -> None:
    user = User.objects.create_user("ada@example.com", PASSWORD)

    assert user.password != PASSWORD
    assert PASSWORD not in user.password
    assert user.check_password(PASSWORD) is True
    assert user.check_password(PASSWORD + "-wrong") is False


def test_user_without_a_password_cannot_log_in_with_one() -> None:
    user = User.objects.create_user("ada@example.com")

    assert user.has_usable_password() is False
    assert user.check_password("") is False
    assert authenticate(email="ada@example.com", password="") is None


def test_extra_fields_are_saved() -> None:
    user = User.objects.create_user(
        "ada@example.com", PASSWORD, first_name="Adaeze", last_name="Ọláńrewájú", country="NG"
    )

    saved = User.objects.get(pk=user.pk)
    assert (saved.first_name, saved.last_name, saved.country) == ("Adaeze", "Ọláńrewájú", "NG")


def test_create_user_can_never_make_staff() -> None:
    user = User.objects.create_user("ada@example.com", PASSWORD, is_staff=True, is_superuser=True)

    assert user.is_staff is False
    assert user.is_superuser is False


@pytest.mark.parametrize("bad_email", ["", "   ", None, 42])
def test_email_is_required(bad_email: Any) -> None:
    with pytest.raises(ValueError, match="email address is required"):
        User.objects.create_user(bad_email, PASSWORD)


@pytest.mark.parametrize("bad_email", ["not-an-email", "ada@", "@example.com", "a b@example.com"])
def test_email_must_look_like_an_email(bad_email: str) -> None:
    with pytest.raises(ValidationError) as caught:
        User.objects.create_user(bad_email, PASSWORD)

    assert "email" in caught.value.message_dict


def test_email_longer_than_254_characters_is_refused() -> None:
    with pytest.raises(ValidationError):
        User.objects.create_user("a" * 250 + "@example.com", PASSWORD)


@pytest.mark.parametrize("bad_country", ["ng", "NGA", "N", "12", "N1"])
def test_country_must_be_two_capital_letters(bad_country: str) -> None:
    with pytest.raises(ValidationError) as caught:
        User.objects.create_user("ada@example.com", PASSWORD, country=bad_country)

    assert "country" in caught.value.message_dict


def test_same_email_twice_is_refused() -> None:
    User.objects.create_user("ada@example.com", PASSWORD)

    with pytest.raises(ValidationError) as caught:
        User.objects.create_user("ada@example.com", PASSWORD)

    assert "email" in caught.value.message_dict
    assert User.objects.count() == 1


def test_same_email_in_different_letter_case_is_refused() -> None:
    User.objects.create_user("ada@example.com", PASSWORD)

    with pytest.raises(ValidationError):
        User.objects.create_user("ADA@Example.com", PASSWORD)

    assert User.objects.count() == 1


def test_a_failed_create_leaves_nothing_behind() -> None:
    with pytest.raises(ValidationError):
        User.objects.create_user("ada@example.com", PASSWORD, country="nigeria")

    assert User.objects.count() == 0


# ---------- create_superuser ----------


def test_create_superuser_is_staff_and_superuser() -> None:
    admin = User.objects.create_superuser("Boss@Example.com", PASSWORD)

    assert admin.email == "boss@example.com"
    assert admin.is_staff is True
    assert admin.is_superuser is True
    assert admin.is_active is True


def test_create_superuser_cannot_be_talked_out_of_it() -> None:
    admin = User.objects.create_superuser(
        "boss@example.com", PASSWORD, is_staff=False, is_superuser=False
    )

    assert admin.is_staff is True
    assert admin.is_superuser is True


@pytest.mark.parametrize("missing", [None, ""])
def test_superuser_needs_a_password(missing: str | None) -> None:
    with pytest.raises(ValueError, match="needs a password"):
        User.objects.create_superuser("boss@example.com", missing)

    assert User.objects.count() == 0


# ---------- finding a user at login ----------


@pytest.mark.parametrize("typed", ["ada@example.com", "ADA@EXAMPLE.COM", "  Ada@Example.com  "])
def test_login_finds_the_user_in_any_letter_case(typed: str) -> None:
    user = User.objects.create_user("ada@example.com", PASSWORD)

    assert User.objects.get_by_natural_key(typed) == user
    assert authenticate(email=typed, password=PASSWORD) == user


def test_wrong_password_does_not_log_in() -> None:
    User.objects.create_user("ada@example.com", PASSWORD)

    assert authenticate(email="ada@example.com", password=PASSWORD + "-wrong") is None


def test_unknown_email_does_not_log_in() -> None:
    assert authenticate(email="nobody@example.com", password=PASSWORD) is None
    assert authenticate(email=None, password=PASSWORD) is None


def test_blocked_user_does_not_log_in() -> None:
    User.objects.create_user("ada@example.com", PASSWORD, is_active=False)

    assert authenticate(email="ada@example.com", password=PASSWORD) is None
