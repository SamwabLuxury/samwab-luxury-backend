"""Tests for apps.accounts.services."""

import pytest

from apps.accounts import services
from apps.accounts.models import User

pytestmark = pytest.mark.django_db

PASSWORD = "correct-horse-battery-9"  # noqa: S105


@pytest.fixture
def user() -> User:
    return User.objects.create_user("ada@example.com", PASSWORD, first_name="Adaeze")


def test_update_profile_saves_the_changes(user: User) -> None:
    services.update_profile(user=user, changes={"first_name": "Ada", "timezone": "Africa/Lagos"})

    fresh = User.objects.get(pk=user.pk)
    assert (fresh.first_name, fresh.timezone) == ("Ada", "Africa/Lagos")


def test_update_profile_moves_updated_at(user: User) -> None:
    before = user.updated_at

    services.update_profile(user=user, changes={"first_name": "Ada"})

    assert User.objects.get(pk=user.pk).updated_at > before


def test_update_profile_with_nothing_does_not_save(user: User) -> None:
    before = user.updated_at

    services.update_profile(user=user, changes={})

    assert User.objects.get(pk=user.pk).updated_at == before


@pytest.mark.parametrize("field", ["email", "is_staff", "signup_intent", "password", "nonsense"])
def test_update_profile_refuses_fields_that_are_not_profile_fields(user: User, field: str) -> None:
    with pytest.raises(ValueError, match="Not profile fields"):
        services.update_profile(user=user, changes={field: "x"})

    assert User.objects.get(pk=user.pk).email == "ada@example.com"
