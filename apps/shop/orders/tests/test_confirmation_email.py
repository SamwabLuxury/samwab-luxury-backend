"""The order confirmation email (build E21).

Figma "Email 01 · Order confirmed": the piece, sales tax, what was paid today, and
"Track the order". Sent once, when Stripe's confirmed payment makes the order paid,
after that change is saved. A mail outage never undoes a payment: the failure is
logged, the order stays unconfirmed by email, and ``send_order_confirmations``
sends whatever was missed.
"""

import logging
from typing import Any

import pytest
from django.core import mail
from django.core.mail import EmailMultiAlternatives
from django.core.management import call_command
from django.test import override_settings

from apps.shop.listings.tests.helpers import make_live_listing, ready_piece
from apps.shop.orders import emails
from apps.shop.orders.models import Order
from apps.shop.orders.tests.helpers import buyer, place_order, stripe_says

pytestmark = pytest.mark.django_db


@pytest.fixture
def commits(django_capture_on_commit_callbacks: Any) -> Any:
    """Run "after the payment is saved" callbacks, as a real request would."""
    return django_capture_on_commit_callbacks


def paid_order(commits: Any, email: str = "ada@example.com", **listing: Any) -> Order:
    order, _ = place_order(
        buyer(email),
        make_live_listing(ready_piece(title="Kelly 28, Gold Togo"), **listing),
    )
    with commits(execute=True):
        stripe_says(order, "succeeded")
    order.refresh_from_db()
    return order


def test_a_paid_order_sends_one_confirmation_to_the_buyer(commits: Any) -> None:
    order = paid_order(commits, ask_minor=1_450_000)

    [message] = mail.outbox
    assert message.to == ["ada@example.com"]
    assert message.subject == f"Your Samwab order {order.order_number} is confirmed"
    assert order.confirmation_sent_at is not None


def test_the_email_says_what_was_bought_and_paid(commits: Any) -> None:
    order = paid_order(commits, ask_minor=1_450_000)

    body = mail.outbox[0].body
    assert order.order_number in body
    assert "Kelly 28, Gold Togo" in body
    assert "$14,500.00" in body
    assert "your own courier" in body
    assert "SAMWAB Luxury, LLC" in body  # the company's legal name (the lead, 26 Nov)


def test_sales_tax_is_shown_only_when_some_was_charged(commits: Any) -> None:
    order = paid_order(commits, ask_minor=1_450_000)
    assert "Sales tax" not in mail.outbox[0].body  # none charged until Stripe Tax is set up

    order.tax_minor = 145_000  # an unsaved copy: as if Stripe Tax had charged 10%
    order.total_minor = order.item_minor + order.tax_minor

    assert "Sales tax: $1,450.00" in emails.render_confirmation(order)[1]


@override_settings(ORDER_PAGE_URL="https://www.samwabluxury.com/account/orders/{order_id}")
def test_the_email_links_to_the_order_page(commits: Any) -> None:
    order = paid_order(commits)

    assert f"https://www.samwabluxury.com/account/orders/{order.pk}" in mail.outbox[0].body


def test_replies_go_to_support_only_when_there_is_a_support_address(commits: Any) -> None:
    paid_order(commits)
    assert mail.outbox[0].reply_to == []
    assert "reply to this email" not in mail.outbox[0].body  # no-reply would bounce it

    with override_settings(SUPPORT_EMAIL="care@samwabluxury.com"):
        order = paid_order(commits, email="bea@example.com")
    message = mail.outbox[1]
    assert message.reply_to == ["care@samwabluxury.com"]
    assert f"reply to this email and quote {order.order_number}" in message.body


def test_there_is_also_a_formatted_version(commits: Any) -> None:
    order = paid_order(commits)

    message = mail.outbox[0]
    assert isinstance(message, EmailMultiAlternatives)
    [(html, kind)] = message.alternatives
    html = str(html)
    assert kind == "text/html"
    assert order.order_number in html
    assert "#2b1712" in html  # the shop's espresso colour


def test_stripe_saying_it_twice_sends_no_second_email(commits: Any) -> None:
    order = paid_order(commits)

    with commits(execute=True):
        stripe_says(order, "succeeded")

    assert len(mail.outbox) == 1


def test_an_unpaid_or_cancelled_order_sends_nothing(commits: Any) -> None:
    order, _ = place_order(buyer())
    with commits(execute=True):
        stripe_says(order, "requires_payment_method")

    assert mail.outbox == []


def resend_is_down(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(message: Any) -> None:
        raise ConnectionError("Resend is down")

    monkeypatch.setattr("apps.shop.orders.emails.deliver", broken)


def test_a_mail_outage_never_undoes_the_payment(
    commits: Any, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    resend_is_down(monkeypatch)
    with caplog.at_level(logging.ERROR):
        order = paid_order(commits)

    assert order.status == "paid"
    assert order.confirmation_sent_at is None  # so it can be sent later
    assert "could not send the confirmation" in caplog.text


def test_the_command_sends_what_was_missed_and_only_once(
    commits: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    with monkeypatch.context() as patch:
        resend_is_down(patch)
        missed = paid_order(commits)
    place_order(buyer("cy@example.com"))  # still waiting for payment: not sent

    call_command("send_order_confirmations")
    call_command("send_order_confirmations")

    assert [m.to for m in mail.outbox] == [["ada@example.com"]]
    missed.refresh_from_db()
    assert missed.confirmation_sent_at is not None
