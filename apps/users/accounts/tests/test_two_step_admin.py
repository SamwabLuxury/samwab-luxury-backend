"""Tests for the admin's second step: every staff member passes it before any admin page."""

from urllib.parse import quote

import pytest
from django.core.cache import cache
from django.test import Client

from apps.users.accounts import selectors, two_step
from apps.users.accounts.models import User
from apps.users.accounts.tests.helpers import (
    PASSWORD,
    admin_login,
    make_staff,
    totp_code,
    turn_on_two_step,
)

pytestmark = pytest.mark.django_db

VERIFY = "/admin/two-step/"
SETUP = "/admin/two-step/setup/"


@pytest.fixture
def staff() -> User:
    user: User = make_staff("grace@samwab.com")
    return user


def wrong_for(secret: str) -> str:
    return "000000" if totp_code(secret) != "000000" else "111111"


# ---------- the gate ----------


def test_staff_without_two_step_are_sent_to_set_it_up(client: Client, staff: User) -> None:
    client.force_login(staff)
    response = client.get("/admin/pieces/piece/?q=kelly")
    assert response.status_code == 302
    assert response["Location"] == f"{SETUP}?next={quote('/admin/pieces/piece/?q=kelly', safe='/')}"


def test_staff_with_two_step_are_asked_for_a_code(client: Client, staff: User) -> None:
    turn_on_two_step(staff)
    client.force_login(staff)
    response = client.get("/admin/")
    assert response.status_code == 302
    assert response["Location"] == f"{VERIFY}?next=/admin/"


def test_after_the_second_step_the_admin_opens(client: Client, staff: User) -> None:
    admin_login(client, staff)
    assert client.get("/admin/").status_code == 200


def test_a_step_passed_by_one_person_does_not_count_for_another(
    client: Client, staff: User
) -> None:
    admin_login(client, staff)
    other = make_staff("ada@samwab.com")
    turn_on_two_step(other)
    session_passed = client.session[two_step.SESSION_PASSED]
    client.force_login(other)  # same browser, different person
    session = client.session
    session[two_step.SESSION_PASSED] = session_passed
    session.save()
    assert client.get("/admin/")["Location"] == f"{VERIFY}?next=/admin/"


def test_a_reset_while_logged_in_sends_them_back_to_set_up(client: Client, staff: User) -> None:
    admin_login(client, staff)
    two_step.turn_off(staff, by=None)
    assert client.get("/admin/")["Location"].startswith(SETUP)


def test_logging_out_needs_no_second_step(client: Client, staff: User) -> None:
    client.force_login(staff)
    response = client.post("/admin/logout/")
    assert response.status_code == 200


def test_the_admin_login_page_needs_no_second_step(client: Client) -> None:
    assert client.get("/admin/login/").status_code == 200


def test_people_who_are_not_staff_see_the_normal_admin_answer(client: Client) -> None:
    client.force_login(User.objects.create_user("ada@example.com", PASSWORD))
    response = client.get("/admin/")
    assert response.status_code == 302
    assert response["Location"].startswith("/admin/login/")


def test_the_api_is_not_behind_the_admin_step(client: Client, staff: User) -> None:
    client.force_login(staff)
    assert client.get("/api/v1/me/").status_code == 200


def test_a_real_password_login_still_works_then_asks_for_the_step(
    client: Client, staff: User
) -> None:
    response = client.post(
        "/admin/login/?next=/admin/",
        {"username": staff.email, "password": PASSWORD, "next": "/admin/"},
    )
    assert response.status_code == 302
    assert response["Location"] == "/admin/"
    assert client.get("/admin/")["Location"] == f"{SETUP}?next=/admin/"


# ---------- the code page ----------


def test_the_code_page_needs_a_logged_in_staff_member(client: Client) -> None:
    response = client.get(VERIFY)
    assert response.status_code == 302
    assert response["Location"] == f"/admin/login/?next={VERIFY}"
    client.force_login(User.objects.create_user("ada@example.com", PASSWORD))
    assert client.get(VERIFY)["Location"] == f"/admin/login/?next={VERIFY}"


def test_the_code_page_shows_a_form(client: Client, staff: User) -> None:
    turn_on_two_step(staff)
    client.force_login(staff)
    response = client.get(f"{VERIFY}?next=/admin/")
    assert response.status_code == 200
    page = response.content.decode()
    assert "authenticator app" in page
    assert 'name="code"' in page
    assert 'autocomplete="one-time-code"' in page


def test_the_right_code_opens_the_page_asked_for(client: Client, staff: User) -> None:
    secret, _ = turn_on_two_step(staff)
    cache.clear()
    client.force_login(staff)
    key_before = client.session.session_key
    response = client.post(f"{VERIFY}?next=/admin/pieces/", {"code": totp_code(secret)})
    assert response.status_code == 302
    assert response["Location"] == "/admin/pieces/"
    assert client.session.session_key != key_before  # a new session id after the step
    assert client.get("/admin/").status_code == 200


def test_a_recovery_code_works_on_the_code_page(client: Client, staff: User) -> None:
    _, codes = turn_on_two_step(staff)
    client.force_login(staff)
    response = client.post(VERIFY, {"code": codes[3]})
    assert response["Location"] == "/admin/"


def test_a_wrong_code_shows_an_error_and_keeps_the_gate_shut(client: Client, staff: User) -> None:
    secret, _ = turn_on_two_step(staff)
    client.force_login(staff)
    response = client.post(VERIFY, {"code": wrong_for(secret)})
    assert response.status_code == 200
    assert "That code is not right" in response.content.decode()
    assert client.get("/admin/")["Location"].startswith(VERIFY)


def test_too_many_wrong_codes_answer_429(client: Client, staff: User) -> None:
    secret, _ = turn_on_two_step(staff)
    cache.clear()
    client.force_login(staff)
    for _ in range(two_step.MAX_WRONG_CODES):
        client.post(VERIFY, {"code": wrong_for(secret)})
    response = client.post(VERIFY, {"code": totp_code(secret)})
    assert response.status_code == 429
    assert "Too many wrong codes" in response.content.decode()


@pytest.mark.parametrize(
    "unsafe", ["https://evil.example.com/", "//evil.example.com/", "javascript:alert(1)"]
)
def test_next_never_leaves_the_site(client: Client, staff: User, unsafe: str) -> None:
    _, codes = turn_on_two_step(staff)
    client.force_login(staff)
    response = client.post(f"{VERIFY}?next={quote(unsafe)}", {"code": codes[0]})
    assert response["Location"] == "/admin/"


def test_the_code_page_sends_people_without_two_step_to_setup(client: Client, staff: User) -> None:
    client.force_login(staff)
    assert client.get(f"{VERIFY}?next=/admin/")["Location"] == f"{SETUP}?next=/admin/"


def test_the_code_page_lets_through_someone_who_already_passed(client: Client, staff: User) -> None:
    admin_login(client, staff)
    assert client.get(f"{VERIFY}?next=/admin/pieces/")["Location"] == "/admin/pieces/"


# ---------- setting it up ----------


def test_the_setup_page_shows_a_qr_code_and_the_key(client: Client, staff: User) -> None:
    client.force_login(staff)
    response = client.get(SETUP)
    assert response.status_code == 200
    page = response.content.decode()
    secret = client.session[two_step.SESSION_SECRET]
    assert "<svg" in page
    assert secret[:4] in page  # shown in groups of four, for typing by hand
    # The key stays the same while the page is reloaded, so a scanned code keeps working.
    client.get(SETUP)
    assert client.session[two_step.SESSION_SECRET] == secret


def test_setting_it_up_shows_the_recovery_codes_once(client: Client, staff: User) -> None:
    client.force_login(staff)
    client.get(SETUP)
    secret = client.session[two_step.SESSION_SECRET]
    response = client.post(f"{SETUP}?next=/admin/pieces/", {"code": totp_code(secret)})
    assert response.status_code == 200
    page = response.content.decode()
    assert "recovery codes" in page.lower()
    assert page.count('class="recovery-code"') == 10
    assert 'href="/admin/pieces/"' in page
    assert two_step.SESSION_SECRET not in client.session
    assert selectors.has_two_step_login(staff)
    assert client.get("/admin/").status_code == 200


def test_a_wrong_setup_code_turns_nothing_on(client: Client, staff: User) -> None:
    client.force_login(staff)
    client.get(SETUP)
    secret = client.session[two_step.SESSION_SECRET]
    response = client.post(SETUP, {"code": wrong_for(secret)})
    assert response.status_code == 200
    assert "That code is not right" in response.content.decode()
    assert not selectors.has_two_step_login(staff)


def test_too_many_wrong_setup_codes_answer_429(client: Client, staff: User) -> None:
    client.force_login(staff)
    client.get(SETUP)
    secret = client.session[two_step.SESSION_SECRET]
    for _ in range(two_step.MAX_WRONG_CODES):
        client.post(SETUP, {"code": wrong_for(secret)})
    assert client.post(SETUP, {"code": totp_code(secret)}).status_code == 429


def test_a_setup_post_without_a_key_in_the_session_starts_again(
    client: Client, staff: User
) -> None:
    client.force_login(staff)
    response = client.post(SETUP, {"code": "123456"})
    assert response.status_code == 302
    assert response["Location"] == f"{SETUP}?next=/admin/"
    assert not selectors.has_two_step_login(staff)


def test_an_empty_code_is_a_form_error(client: Client, staff: User) -> None:
    client.force_login(staff)
    client.get(SETUP)
    response = client.post(SETUP, {"code": ""})
    assert response.status_code == 200
    assert not selectors.has_two_step_login(staff)


def test_the_setup_page_is_closed_once_two_step_is_on(client: Client, staff: User) -> None:
    turn_on_two_step(staff)
    client.force_login(staff)
    assert client.get(f"{SETUP}?next=/admin/")["Location"] == f"{VERIFY}?next=/admin/"
    assert client.post(SETUP, {"code": "123456"})["Location"] == f"{VERIFY}?next=/admin/"


def test_the_setup_page_needs_a_logged_in_staff_member(client: Client) -> None:
    assert client.get(SETUP)["Location"] == f"/admin/login/?next={SETUP}"
