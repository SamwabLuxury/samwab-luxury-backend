"""Tests for apps.accounts.selectors: roles and onboarding steps."""

import pytest
from django.contrib.auth.models import Group

from apps.accounts import roles, selectors
from apps.accounts.models import User

pytestmark = pytest.mark.django_db

PASSWORD = "correct-horse-battery-9"  # noqa: S105


@pytest.fixture
def user() -> User:
    return User.objects.create_user("ada@example.com", PASSWORD)


def test_a_new_user_has_no_roles(user: User) -> None:
    assert selectors.get_roles(user) == []


def test_every_role_can_be_held_and_comes_back_in_order(user: User) -> None:
    user.groups.add(*Group.objects.filter(name__in=roles.ALL_ROLES))

    assert selectors.get_roles(user) == list(roles.ALL_ROLES)


def test_a_dealer_who_also_owns_holds_both(user: User) -> None:
    user.groups.add(Group.objects.get(name=roles.DEALER), Group.objects.get(name=roles.OWNER))

    assert selectors.get_roles(user) == [roles.OWNER, roles.DEALER]


def test_buyer_has_no_steps(user: User) -> None:
    assert selectors.get_next_steps(user) == []


def test_owner_steps_until_the_owner_role(user: User) -> None:
    user.signup_intent = "owner"

    assert selectors.get_next_steps(user) == ["accept_terms", "identity_check", "payout_account"]
    user.groups.add(Group.objects.get(name=roles.OWNER))
    assert selectors.get_next_steps(user) == []


def test_dealer_steps_until_the_dealer_role(user: User) -> None:
    user.signup_intent = "dealer"

    assert selectors.get_next_steps(user) == ["identity_check", "dealer_application"]
    user.groups.add(Group.objects.get(name=roles.DEALER))
    assert selectors.get_next_steps(user) == []


def test_owner_role_does_not_finish_dealer_onboarding(user: User) -> None:
    user.signup_intent = "dealer"
    user.groups.add(Group.objects.get(name=roles.OWNER))

    assert selectors.get_next_steps(user) == ["identity_check", "dealer_application"]


def test_steps_are_plain_strings(user: User) -> None:
    user.signup_intent = "owner"

    assert all(type(step) is str for step in selectors.get_next_steps(user))


def test_two_step_login_is_off_until_build_06(user: User) -> None:
    assert selectors.has_two_step_login(user) is False
