"""Reads about users. Nothing here changes data."""

from allauth.mfa.models import Authenticator
from django.conf import settings

from apps.users.accounts import roles
from apps.users.accounts.enums import NextStep, SignupIntent
from apps.users.accounts.models import User
from apps.users.legal import selectors as legal
from apps.users.legal.enums import DocumentKind


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

    ``accept_terms`` is listed for anyone while a sign-up text in force (terms of
    service, privacy policy) is not accepted, and for an owner until she has accepted
    the consignment agreement in force (build 11). The records behind the other steps
    (ID checks, payout accounts, dealer applications) arrive in later builds; until
    then they are listed until the matching role is granted.
    """
    held = set(get_roles(user))
    steps: list[str] = []

    if legal.missing(user, settings.LEGAL_SIGNUP_DOCUMENTS):
        steps.append(NextStep.ACCEPT_TERMS)

    if user.signup_intent == SignupIntent.OWNER and roles.OWNER not in held:
        if not legal.has_accepted_current(user, DocumentKind.CONSIGNMENT_AGREEMENT):
            steps.append(NextStep.ACCEPT_TERMS)
        steps += [NextStep.IDENTITY_CHECK, NextStep.PAYOUT_ACCOUNT]

    if user.signup_intent == SignupIntent.DEALER and roles.DEALER not in held:
        steps += [NextStep.IDENTITY_CHECK, NextStep.DEALER_APPLICATION]

    # Keep the first appearance of each step.
    return [str(step) for step in dict.fromkeys(steps)]


def has_two_step_login(user: User) -> bool:
    """Whether the user has an authenticator app set up for two-step login.

    Recovery codes alone do not count: they come with the app and are its backup.
    """
    return bool(Authenticator.objects.filter(user=user, type=Authenticator.Type.TOTP).exists())
