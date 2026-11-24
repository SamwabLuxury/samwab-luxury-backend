"""Two-step login (build 06): after the password, a 6-digit code from an
authenticator app, or one of 10 one-time recovery codes.

allauth.mfa stores and checks the codes (its ``Authenticator`` table, with the app
key encrypted by ``mfa_adapter``). This module adds what allauth leaves to us:
turning it on from the admin, a limit on wrong codes, the audit trail, a reset for
a lost phone, and the session mark that the admin's gate
(``middleware.AdminTwoStepMiddleware``) looks for.
"""

import base64
import secrets

from allauth.mfa.adapter import get_adapter
from allauth.mfa.models import Authenticator
from allauth.mfa.recovery_codes.internal.auth import RecoveryCodes
from allauth.mfa.totp.internal.auth import TOTP, validate_totp_code
from django.core.cache import cache
from django.db import transaction
from django.http import HttpRequest

from apps.platform.audit import services as audit
from apps.users.accounts import selectors
from apps.users.accounts.models import User

# In the session: the id of the person whose second step passed, and the key shown
# on the set-up page until she types her first code.
SESSION_PASSED = "samwab.two_step_passed"
SESSION_SECRET = "samwab.two_step_setup_secret"  # noqa: S105 (a session key name)

# Five wrong codes in a row lock the second step for 15 minutes. A 6-digit code
# guessed five times in 15 minutes has a 1 in 200,000 chance.
MAX_WRONG_CODES = 5
LOCK_SECONDS = 15 * 60

# Longest code worth checking: a recovery code is 8 digits.
_MAX_CODE_LENGTH = 20


class TooManyWrongCodesError(Exception):
    """Too many wrong codes recently; the second step waits for the lock to end."""


class TwoStepAlreadyOnError(Exception):
    """Two-step login is already on for this person; reset it first."""


def new_secret() -> str:
    """A new authenticator app key: 20 random bytes as 32 base32 characters (RFC 4226)."""
    return base64.b32encode(secrets.token_bytes(20)).decode()


def setup_link(user: User, secret: str) -> str:
    """The ``otpauth://`` link an authenticator app reads from the QR code."""
    return str(get_adapter().build_totp_url(user, secret))


def qr_svg(link: str) -> str:
    """The QR code for ``link``, as SVG markup (allauth's adapter, the qrcode package)."""
    return str(get_adapter().build_totp_svg(link))


@transaction.atomic
def turn_on(user: User, secret: str, code: str) -> list[str] | None:
    """Turn two-step login on with ``secret`` once ``code`` proves the app has it.

    Returns the 10 recovery codes (show them once), or None for a wrong code.
    """
    User.objects.select_for_update().get(pk=user.pk)  # one set-up at a time per person
    if selectors.has_two_step_login(user):
        raise TwoStepAlreadyOnError()
    _check_not_locked(user)
    if not validate_totp_code(secret, _clean(code)):
        _count_wrong_code(user)
        return None
    _clear_wrong_codes(user)
    TOTP.activate(user, secret)
    codes = [str(code) for code in RecoveryCodes.activate(user).get_unused_codes()]
    audit.record("two_step_enabled", user, by=user)
    return codes


def check_code(user: User, code: str) -> str | None:
    """Check a second-step code. Returns ``"totp"`` or ``"recovery_code"``, else None.

    Each code works once: allauth remembers app codes for their 30 seconds and marks
    recovery codes used.
    """
    _check_not_locked(user)
    code = _clean(code)
    if code and len(code) <= _MAX_CODE_LENGTH:
        for authenticator in _authenticators(user):
            if authenticator.wrap().validate_code(code):
                authenticator.record_usage()
                _clear_wrong_codes(user)
                if authenticator.type == Authenticator.Type.RECOVERY_CODES:
                    audit.record("two_step_recovery_code_used", user, by=user)
                    return "recovery_code"
                return "totp"
    _count_wrong_code(user)
    return None


@transaction.atomic
def turn_off(user: User, *, by: User | None) -> int:
    """Remove her authenticator app and recovery codes (a lost phone).

    Staff then set it up again at their next admin page. Returns how many were removed.
    """
    removed, _ = Authenticator.objects.filter(user=user).delete()
    if removed:
        audit.record("two_step_reset", user, by=by)
    return int(removed)


def mark_passed(request: HttpRequest) -> None:
    """Record in the session that this person passed the second step.

    The session gets a new id first, as Django does at login, because the session
    now carries more trust than before.
    """
    request.session.cycle_key()
    request.session[SESSION_PASSED] = str(request.user.pk)


def has_passed(request: HttpRequest) -> bool:
    return request.session.get(SESSION_PASSED) == str(request.user.pk)


def _authenticators(user: User) -> list[Authenticator]:
    # The app first: it is what people use every day.
    found = Authenticator.objects.filter(
        user=user, type__in=[Authenticator.Type.TOTP, Authenticator.Type.RECOVERY_CODES]
    )
    return sorted(found, key=lambda item: item.type != Authenticator.Type.TOTP)


def _clean(code: str) -> str:
    return "".join(code.split())


def _wrong_codes_key(user: User) -> str:
    return f"samwab.two_step.wrong_codes.{user.pk}"


def _check_not_locked(user: User) -> None:
    if cache.get(_wrong_codes_key(user), 0) >= MAX_WRONG_CODES:
        raise TooManyWrongCodesError()


def _count_wrong_code(user: User) -> None:
    key = _wrong_codes_key(user)
    cache.add(key, 0, timeout=LOCK_SECONDS)
    cache.incr(key)


def _clear_wrong_codes(user: User) -> None:
    cache.delete(_wrong_codes_key(user))
