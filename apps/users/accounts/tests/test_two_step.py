"""Tests for two-step login: turning it on, checking codes, wrong-code limits, reset."""

import time

import pytest
from allauth.mfa.models import Authenticator
from django.core.cache import cache

from apps.platform.audit.models import AuditEvent
from apps.platform.core import encryption
from apps.users.accounts import selectors, two_step
from apps.users.accounts.models import User
from apps.users.accounts.tests.helpers import PASSWORD, make_staff, totp_code, turn_on_two_step

pytestmark = pytest.mark.django_db


@pytest.fixture
def ada() -> User:
    return User.objects.create_user("ada@example.com", PASSWORD)


def actions(user: User) -> list[str]:
    return list(
        AuditEvent.objects.filter(object_id=user.pk).order_by("id").values_list("action", flat=True)
    )


def test_a_new_secret_is_32_base32_characters() -> None:
    secret = two_step.new_secret()
    assert len(secret) == 32
    assert set(secret) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567")
    assert two_step.new_secret() != secret


def test_nobody_has_two_step_login_at_first(ada: User) -> None:
    assert selectors.has_two_step_login(ada) is False


def test_turning_it_on_with_the_right_code_gives_ten_recovery_codes(ada: User) -> None:
    secret = two_step.new_secret()
    codes = two_step.turn_on(ada, secret, totp_code(secret))
    assert codes is not None
    assert len(codes) == 10
    assert all(len(code) == 8 and code.isdigit() for code in codes)
    assert selectors.has_two_step_login(ada) is True
    types = set(Authenticator.objects.filter(user=ada).values_list("type", flat=True))
    assert types == {Authenticator.Type.TOTP, Authenticator.Type.RECOVERY_CODES}
    assert actions(ada) == ["accounts.user.two_step_enabled"]
    event = AuditEvent.objects.get(action="accounts.user.two_step_enabled")
    assert event.actor == ada
    assert event.changes == {}


def test_a_wrong_code_turns_nothing_on(ada: User) -> None:
    secret = two_step.new_secret()
    wrong = "000000" if totp_code(secret) != "000000" else "111111"
    assert two_step.turn_on(ada, secret, wrong) is None
    assert not Authenticator.objects.filter(user=ada).exists()
    assert actions(ada) == []


def test_turning_it_on_twice_is_refused(ada: User) -> None:
    turn_on_two_step(ada)
    secret = two_step.new_secret()
    with pytest.raises(two_step.TwoStepAlreadyOnError):
        two_step.turn_on(ada, secret, totp_code(secret))
    assert Authenticator.objects.filter(user=ada, type=Authenticator.Type.TOTP).count() == 1


def test_the_secret_is_stored_encrypted(ada: User) -> None:
    secret, _ = turn_on_two_step(ada)
    stored = Authenticator.objects.get(user=ada, type=Authenticator.Type.TOTP).data["secret"]
    assert secret not in stored
    assert encryption.decrypt(stored) == secret


def test_the_app_code_is_accepted_once(ada: User) -> None:
    secret, _ = turn_on_two_step(ada)
    cache.clear()  # the setup code may be the same as the next one
    code = totp_code(secret)
    assert two_step.check_code(ada, code) == "totp"
    assert two_step.check_code(ada, code) is None  # a code seen once is used up


def test_the_code_from_the_previous_30_seconds_is_refused(ada: User) -> None:
    secret, _ = turn_on_two_step(ada)
    cache.clear()
    old = totp_code(secret, at=time.time() - 60)
    if old != totp_code(secret):
        assert two_step.check_code(ada, old) is None


def test_spaces_around_and_inside_a_code_are_ignored(ada: User) -> None:
    secret, _ = turn_on_two_step(ada)
    cache.clear()
    code = totp_code(secret)
    assert two_step.check_code(ada, f" {code[:3]} {code[3:]} ") == "totp"


def test_a_recovery_code_works_once_and_is_audited(ada: User) -> None:
    _, codes = turn_on_two_step(ada)
    assert two_step.check_code(ada, codes[0]) == "recovery_code"
    assert two_step.check_code(ada, codes[0]) is None
    assert two_step.check_code(ada, codes[1]) == "recovery_code"
    assert actions(ada) == [
        "accounts.user.two_step_enabled",
        "accounts.user.two_step_recovery_code_used",
        "accounts.user.two_step_recovery_code_used",
    ]


def test_a_code_for_someone_without_two_step_is_refused(ada: User) -> None:
    assert two_step.check_code(ada, "123456") is None


@pytest.mark.parametrize("code", ["", "   ", "abcdef", "1" * 200])
def test_nonsense_codes_are_refused(ada: User, code: str) -> None:
    turn_on_two_step(ada)
    assert two_step.check_code(ada, code) is None


def test_five_wrong_codes_lock_the_second_step_for_fifteen_minutes(ada: User) -> None:
    secret, _ = turn_on_two_step(ada)
    cache.clear()
    wrong = "000000" if totp_code(secret) != "000000" else "111111"
    for _ in range(two_step.MAX_WRONG_CODES):
        assert two_step.check_code(ada, wrong) is None
    with pytest.raises(two_step.TooManyWrongCodesError):
        two_step.check_code(ada, totp_code(secret))  # even the right code waits
    assert two_step.LOCK_SECONDS == 15 * 60


def test_the_limit_counts_each_person_separately(ada: User) -> None:
    turn_on_two_step(ada)
    grace = make_staff("grace@samwab.com")
    grace_secret, _ = turn_on_two_step(grace)
    cache.clear()
    for _ in range(two_step.MAX_WRONG_CODES):
        two_step.check_code(ada, "999999x")
    assert two_step.check_code(grace, totp_code(grace_secret)) == "totp"


def test_a_right_code_clears_earlier_wrong_ones(ada: User) -> None:
    secret, _ = turn_on_two_step(ada)
    cache.clear()
    for _ in range(two_step.MAX_WRONG_CODES - 1):
        two_step.check_code(ada, "999999x")
    assert two_step.check_code(ada, totp_code(secret)) == "totp"
    for _ in range(two_step.MAX_WRONG_CODES - 1):
        two_step.check_code(ada, "999999x")
    assert two_step.check_code(ada, "999999x") is None  # not locked yet: the count restarted


def test_wrong_setup_codes_count_towards_the_limit(ada: User) -> None:
    secret = two_step.new_secret()
    for _ in range(two_step.MAX_WRONG_CODES):
        two_step.turn_on(ada, secret, "999999x")
    with pytest.raises(two_step.TooManyWrongCodesError):
        two_step.turn_on(ada, secret, totp_code(secret))


def test_turning_it_off_removes_everything_and_is_audited(ada: User) -> None:
    turn_on_two_step(ada)
    assert two_step.turn_off(ada, by=None) == 2
    assert not Authenticator.objects.filter(user=ada).exists()
    assert selectors.has_two_step_login(ada) is False
    event = AuditEvent.objects.get(action="accounts.user.two_step_reset")
    assert event.actor is None


def test_turning_it_off_when_it_was_off_records_nothing(ada: User) -> None:
    assert two_step.turn_off(ada, by=None) == 0
    assert actions(ada) == []


def test_the_qr_code_is_an_svg_naming_samwab_and_the_email(ada: User) -> None:
    secret = two_step.new_secret()
    url = two_step.setup_link(ada, secret)
    assert url.startswith("otpauth://totp/")
    assert "Samwab" in url
    assert "ada%40example.com" in url or "ada@example.com" in url
    assert f"secret={secret}" in url
    svg = two_step.qr_svg(url)
    assert svg.lstrip().startswith("<svg") or svg.lstrip().startswith("<?xml")
    assert "</svg>" in svg
