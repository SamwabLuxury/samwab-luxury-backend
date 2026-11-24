"""Reads about users. Nothing here changes data."""

from allauth.mfa.models import Authenticator

from apps.users.accounts import roles
from apps.users.accounts.enums import NextStep, SignupIntent
from apps.users.accounts.models import User


def get_roles(user: User) -> list[str]:
    """The roles this user holds, in the API's order.

    A role is a Django group with a known role name. Any other group is ignored.
    """
    names = set(user.groups.values_list("name", flat=True))
    return [role for role in roles.ALL_ROLES if role in names]


def get_next_steps(user: User) -> list[str]:
    """What this user still has to do for the onboarding she chose at sign-up.

    The web app uses this to choose her next screen. An empty list means
    nothing is waiting.

    The records behind each step (accepted terms, ID checks, payout accounts,
    dealer applications) arrive in later builds. Until then, every step of the
    chosen onboarding is listed until the matching role is granted.
    """
    held = set(get_roles(user))
    steps: list[str] = []

    if user.signup_intent == SignupIntent.OWNER and roles.OWNER not in held:
        steps += [NextStep.ACCEPT_TERMS, NextStep.IDENTITY_CHECK, NextStep.PAYOUT_ACCOUNT]

    if user.signup_intent == SignupIntent.DEALER and roles.DEALER not in held:
        steps += [NextStep.IDENTITY_CHECK, NextStep.DEALER_APPLICATION]

    # Keep the first appearance of each step.
    return [str(step) for step in dict.fromkeys(steps)]


def has_two_step_login(user: User) -> bool:
    """Whether the user has an authenticator app set up for two-step login.

    Recovery codes alone do not count: they come with the app and are its backup.
    """
    return bool(Authenticator.objects.filter(user=user, type=Authenticator.Type.TOTP).exists())
