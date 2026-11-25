"""The mailing list (D46, D51 #5: approved by the lead 25 Nov).

"Join the list" in the footer. Members see a drop 24 hours before everyone else
(drops come next). Joining sends a confirmation email (double opt-in): only a
confirmed member is on the list. Every email carries an unsubscribe link that
works for good.

The join answer is the same whatever the email's state, so nobody can use it to
find out who is on the list. A confirmation is sent at most once every 10 minutes
per address, so the form cannot be used to flood someone's inbox.
"""

import re
from datetime import timedelta
from typing import Any

import pytest
from django.core import mail, signing
from django.db import IntegrityError, transaction
from django.test import Client, override_settings
from django.utils import timezone

from apps.users.mailing_list import selectors
from apps.users.mailing_list.models import ListMember
from apps.users.mailing_list.tokens import confirm_token, unsubscribe_token

pytestmark = pytest.mark.django_db

JOIN = "/api/v1/mailing-list/"
CONFIRM = "/api/v1/mailing-list/confirm/"
UNSUBSCRIBE = "/api/v1/mailing-list/unsubscribe/"


def join(client: Client, email: str, **extra: Any) -> Any:
    return client.post(JOIN, {"email": email, **extra}, content_type="application/json")


def use(client: Client, path: str, token: str) -> Any:
    return client.post(path, {"token": token}, content_type="application/json")


def token_in(message: Any, kind: str) -> str:
    match = re.search(rf"/mailing-list/{kind}/([^\s]+)", message.body)
    assert match, message.body
    return match.group(1)


def test_joining_sends_a_confirmation_email(client: Client) -> None:
    response = join(client, "  Ada@Example.com ")

    assert response.status_code == 202, response.content
    assert response.json() == {"status": "check_your_email"}
    member = ListMember.objects.get()
    assert (member.email, member.status) == ("ada@example.com", "pending")
    [message] = mail.outbox
    assert message.to == ["ada@example.com"]
    assert "confirm" in message.subject.lower()
    assert "http://localhost:3000/mailing-list/confirm/" in message.body
    assert "http://localhost:3000/mailing-list/unsubscribe/" in message.body
    assert not selectors.is_member("ada@example.com")  # not until confirmed


def test_confirming_puts_me_on_the_list(client: Client) -> None:
    join(client, "ada@example.com")
    token = token_in(mail.outbox[0], "confirm")

    response = use(client, CONFIRM, token)

    assert response.status_code == 200, response.content
    assert response.json() == {"email": "ada@example.com", "status": "confirmed"}
    member = ListMember.objects.get()
    assert member.status == "confirmed"
    assert member.confirmed_at is not None
    assert selectors.is_member("ADA@example.com")


def test_confirming_twice_is_fine(client: Client) -> None:
    join(client, "ada@example.com")
    token = token_in(mail.outbox[0], "confirm")
    use(client, CONFIRM, token)
    first = ListMember.objects.get().confirmed_at

    again = use(client, CONFIRM, token)

    assert again.status_code == 200
    assert ListMember.objects.get().confirmed_at == first


def test_the_unsubscribe_link_takes_me_off_and_keeps_working(client: Client) -> None:
    join(client, "ada@example.com")
    client.post(
        CONFIRM, {"token": token_in(mail.outbox[0], "confirm")}, content_type="application/json"
    )
    token = token_in(mail.outbox[0], "unsubscribe")

    response = use(client, UNSUBSCRIBE, token)
    again = use(client, UNSUBSCRIBE, token)

    assert response.status_code == again.status_code == 200
    assert response.json() == {"email": "ada@example.com", "status": "unsubscribed"}
    member = ListMember.objects.get()
    assert member.status == "unsubscribed"
    assert member.unsubscribed_at is not None
    assert not selectors.is_member("ada@example.com")


def test_an_old_confirmation_link_cannot_put_me_back_after_unsubscribing(client: Client) -> None:
    join(client, "ada@example.com")
    confirm = token_in(mail.outbox[0], "confirm")
    client.post(
        UNSUBSCRIBE,
        {"token": token_in(mail.outbox[0], "unsubscribe")},
        content_type="application/json",
    )

    response = use(client, CONFIRM, confirm)

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_link"
    assert ListMember.objects.get().status == "unsubscribed"


def test_joining_again_after_unsubscribing_asks_to_confirm_again(client: Client) -> None:
    join(client, "ada@example.com")
    client.post(
        UNSUBSCRIBE,
        {"token": token_in(mail.outbox[0], "unsubscribe")},
        content_type="application/json",
    )
    ListMember.objects.update(confirm_sent_at=timezone.now() - timedelta(minutes=11))

    join(client, "ada@example.com")

    assert ListMember.objects.get().status == "pending"
    assert len(mail.outbox) == 2


@pytest.mark.parametrize("state", ["pending", "confirmed", "unsubscribed"])
def test_the_join_answer_never_tells_who_is_on_the_list(client: Client, state: str) -> None:
    ListMember.objects.create(
        email="ada@example.com", status=state, confirm_sent_at=timezone.now() - timedelta(hours=1)
    )

    response = join(client, "ada@example.com")

    assert response.status_code == 202
    assert response.json() == {"status": "check_your_email"}


def test_a_confirmed_member_gets_no_new_email(client: Client) -> None:
    ListMember.objects.create(email="ada@example.com", status="confirmed")

    join(client, "ada@example.com")

    assert mail.outbox == []


def test_at_most_one_confirmation_every_10_minutes(client: Client) -> None:
    join(client, "ada@example.com")
    join(client, "ada@example.com")
    join(client, "ada@example.com")
    assert len(mail.outbox) == 1

    ListMember.objects.update(confirm_sent_at=timezone.now() - timedelta(minutes=11))
    join(client, "ada@example.com")

    assert len(mail.outbox) == 2


def test_a_confirmation_link_expires_after_7_days(client: Client) -> None:
    join(client, "ada@example.com")
    token = token_in(mail.outbox[0], "confirm")

    with override_settings(MAILING_LIST_CONFIRM_DAYS=0):
        response = use(client, CONFIRM, token)

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_link"


@pytest.mark.parametrize(
    "token",
    [
        "nonsense",
        signing.dumps("ada@example.com", salt="something-else"),
        unsubscribe_token("ada@example.com"),  # an unsubscribe link is not a confirm link
    ],
)
def test_a_bad_or_wrong_kind_of_link_is_refused(client: Client, token: str) -> None:
    join(client, "ada@example.com")

    response = use(client, CONFIRM, token)

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_link"
    assert ListMember.objects.get().status == "pending"


def test_a_link_for_an_address_not_on_the_list_is_refused(client: Client) -> None:
    for path, token in (
        (CONFIRM, confirm_token("ghost@example.com")),
        (UNSUBSCRIBE, unsubscribe_token("ghost@example.com")),
    ):
        response = client.post(path, {"token": token}, content_type="application/json")
        assert response.status_code == 400
        assert response.json()["code"] == "invalid_link"


@pytest.mark.parametrize("email", ["", "not-an-email", "a" * 250 + "@example.com"])
def test_a_bad_email_is_refused(client: Client, email: str) -> None:
    response = join(client, email)

    assert response.status_code == 400
    assert response.json()["errors"][0]["field"] == "email"
    assert not ListMember.objects.exists()


def test_where_they_joined_from_is_kept(client: Client) -> None:
    join(client, "ada@example.com", source="footer")

    assert ListMember.objects.get().source == "footer"


def test_no_login_is_needed(client: Client) -> None:
    assert join(client, "ada@example.com").status_code == 202


def test_if_the_email_cannot_be_sent_the_join_still_answers_and_it_is_logged(
    client: Client, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def broken(*args: Any, **kwargs: Any) -> int:
        raise OSError("mail server down")

    monkeypatch.setattr("apps.users.mailing_list.services.send_mail", broken)

    response = join(client, "ada@example.com")

    assert response.status_code == 202
    assert "could not send" in caplog.text
    assert ListMember.objects.get().confirm_sent_at is None  # so the next try sends again


def test_one_row_per_address() -> None:
    ListMember.objects.create(email="ada@example.com")

    with pytest.raises(IntegrityError), transaction.atomic():
        ListMember.objects.create(email="ada@example.com")


def test_the_database_refuses_an_unknown_status() -> None:
    member = ListMember.objects.create(email="ada@example.com")

    with pytest.raises(IntegrityError), transaction.atomic():
        ListMember.objects.filter(pk=member.pk).update(status="maybe")


def test_the_table_and_its_text() -> None:
    member = ListMember.objects.create(email="ada@example.com")

    assert ListMember._meta.db_table == "mailing_list_members"
    assert str(member) == "ada@example.com (pending)"


def test_staff_see_the_list_but_cannot_add_or_edit(admin_client_two_step: Client) -> None:
    ListMember.objects.create(email="ada@example.com", status="confirmed")

    page = admin_client_two_step.get("/admin/mailing_list/listmember/")
    add = admin_client_two_step.get("/admin/mailing_list/listmember/add/")

    assert page.status_code == 200
    assert "ada@example.com" in page.content.decode()
    assert add.status_code == 403


@pytest.mark.parametrize("kind", ["nonsense", "a confirm link"])
def test_a_bad_unsubscribe_link_is_refused(client: Client, kind: str) -> None:
    join(client, "ada@example.com")
    link = confirm_token("ada@example.com") if kind == "a confirm link" else "nonsense"

    response = use(client, UNSUBSCRIBE, link)

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_link"
    assert ListMember.objects.get().status == "pending"
