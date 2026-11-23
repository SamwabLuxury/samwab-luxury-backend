"""Tests for apps.users.accounts.models.User: its shape and the rules the database enforces."""

import uuid

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

from apps.platform.core.models import BaseModel
from apps.users.accounts.models import User

PASSWORD = "correct-horse-battery-staple"  # noqa: S105


def test_this_is_the_projects_user_model() -> None:
    assert settings.AUTH_USER_MODEL == "accounts.User"
    assert get_user_model() is User


def test_login_is_by_email_and_there_is_no_username() -> None:
    assert User.USERNAME_FIELD == "email"
    assert User.REQUIRED_FIELDS == []
    assert "username" not in {field.name for field in User._meta.get_fields()}


def test_table_is_called_users() -> None:
    assert User._meta.db_table == "users"


def test_user_builds_on_base_model() -> None:
    assert issubclass(User, BaseModel)


def test_no_role_is_stored_on_the_user() -> None:
    """Roles are worked out from what a person has completed, never stored."""
    assert "role" not in {field.name for field in User._meta.get_fields()}


def test_text_form_is_the_email() -> None:
    assert str(User(email="ada@example.com")) == "ada@example.com"


@pytest.mark.django_db
def test_id_is_a_uuid_version_7_and_timestamps_are_set() -> None:
    user = User.objects.create_user("ada@example.com", PASSWORD)

    assert isinstance(user.id, uuid.UUID)
    assert user.id.version == 7
    assert user.created_at is not None
    assert user.updated_at is not None
    assert user.created_at.tzinfo is not None


@pytest.mark.django_db
def test_newer_users_sort_after_older_ones_by_id() -> None:
    first = User.objects.create_user("first@example.com", PASSWORD)
    second = User.objects.create_user("second@example.com", PASSWORD)
    third = User.objects.create_user("third@example.com", PASSWORD)

    assert list(User.objects.order_by("id")) == [first, second, third]


@pytest.mark.django_db
def test_database_refuses_a_duplicate_email_even_without_the_manager() -> None:
    """The manager checks first, but the database is the last line of defence."""
    User.objects.create_user("ada@example.com", PASSWORD)

    with pytest.raises(IntegrityError), transaction.atomic():
        User(email="ada@example.com").save()

    assert User.objects.count() == 1


@pytest.mark.django_db
def test_database_refuses_an_email_that_is_not_lowercase() -> None:
    """Login looks emails up in lowercase, so a mixed-case row could never log in."""
    with pytest.raises(IntegrityError), transaction.atomic():
        User(email="ADA@example.com").save()

    assert User.objects.count() == 0


def test_checking_a_user_makes_the_email_lowercase() -> None:
    user = User(email="  Ada@Example.COM ")

    user.clean()

    assert user.email == "ada@example.com"


@pytest.mark.django_db
def test_a_user_can_be_put_in_a_staff_group() -> None:
    from django.contrib.auth.models import Group

    reviewers = Group.objects.create(name="Reviewers")
    user = User.objects.create_user("ada@example.com", PASSWORD)

    user.groups.add(reviewers)

    assert list(user.groups.all()) == [reviewers]
    assert list(reviewers.user_set.all()) == [user]


def test_signup_intent_defaults_to_buyer() -> None:
    assert User(email="ada@example.com").signup_intent == "buyer"


@pytest.mark.django_db
def test_database_refuses_an_unknown_signup_intent() -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        User(email="ada@example.com", signup_intent="admin").save()

    assert User.objects.count() == 0


def test_passwords_are_hashed_with_argon2_outside_tests() -> None:
    """Tests use a fast hash on purpose; real settings must put Argon2 first."""
    from configurations.settings import base

    assert base.PASSWORD_HASHERS[0] == "django.contrib.auth.hashers.Argon2PasswordHasher"


def test_argon2_works_on_this_machine() -> None:
    """The argon2-cffi package is installed and Django's Argon2 hasher can use it."""
    from django.contrib.auth.hashers import Argon2PasswordHasher

    hasher = Argon2PasswordHasher()
    hashed = hasher.encode(PASSWORD, hasher.salt())

    assert hashed.startswith("argon2$")
    assert hasher.verify(PASSWORD, hashed) is True
    assert hasher.verify(PASSWORD + "x", hashed) is False
