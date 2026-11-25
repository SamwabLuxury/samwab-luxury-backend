"""Email through Resend's HTTPS API (build E14; the lead chose Resend, 25 Nov).

Render's free plan blocks the SMTP ports (25, 465, 587) since September 2025, so we
send with Resend's API: POST https://api.resend.com/emails with the API key as a
Bearer token. A fake stands in for Resend here; no test reaches the network.
"""

import io
import json
import urllib.error
from typing import Any

import pytest
from django.core import mail
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.core.management import CommandError, call_command
from django.test import override_settings

from apps.platform.core.mail import ResendEmailBackend, ResendError


class FakeResend:
    """Records each request and answers with the next prepared reply."""

    def __init__(self, *replies: tuple[int, dict[str, Any]]) -> None:
        self.replies = list(replies) or [(200, {"id": "49a3999c-0ce1"})]
        self.requests: list[Any] = []

    def __call__(self, request: Any, timeout: float) -> Any:
        self.requests.append(request)
        self.timeout = timeout
        status, body = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        payload = io.BytesIO(json.dumps(body).encode())
        if status >= 400:
            raise urllib.error.HTTPError(request.full_url, status, "error", {}, payload)  # type: ignore[arg-type]
        return payload

    def body(self, index: int = 0) -> dict[str, Any]:
        sent: dict[str, Any] = json.loads(self.requests[index].data)
        return sent


@pytest.fixture
def resend(monkeypatch: pytest.MonkeyPatch) -> FakeResend:
    fake = FakeResend()
    monkeypatch.setattr("apps.platform.core.mail.urllib.request.urlopen", fake)
    monkeypatch.setattr("apps.platform.core.mail.time.sleep", lambda seconds: None)
    return fake


def backend() -> ResendEmailBackend:
    return ResendEmailBackend(api_key="re_made_up_key")


def test_a_plain_email_becomes_one_api_call(resend: FakeResend) -> None:
    message = EmailMessage(
        "Confirm you want the Samwab list",
        "Hello,\nopen this link.",
        "Samwab <no-reply@samwabluxury.com>",
        ["ada@example.com"],
        cc=["cc@example.com"],
        bcc=["bcc@example.com"],
        reply_to=["help@samwabluxury.com"],
    )

    sent = backend().send_messages([message])

    assert sent == 1
    [request] = resend.requests
    assert request.full_url == "https://api.resend.com/emails"
    assert request.get_method() == "POST"
    assert request.get_header("Authorization") == "Bearer re_made_up_key"
    assert request.get_header("Content-type") == "application/json"
    assert request.get_header("User-agent").startswith("samwab-backend")
    assert resend.body() == {
        "from": "Samwab <no-reply@samwabluxury.com>",
        "to": ["ada@example.com"],
        "cc": ["cc@example.com"],
        "bcc": ["bcc@example.com"],
        "reply_to": ["help@samwabluxury.com"],
        "subject": "Confirm you want the Samwab list",
        "text": "Hello,\nopen this link.",
    }
    assert resend.timeout == 10


def test_an_html_version_is_sent_too(resend: FakeResend) -> None:
    message = EmailMultiAlternatives("Hi", "plain", "a@samwabluxury.com", ["b@example.com"])
    message.attach_alternative("<p>rich</p>", "text/html")

    backend().send_messages([message])

    assert resend.body()["text"] == "plain"
    assert resend.body()["html"] == "<p>rich</p>"


def test_an_html_only_email(resend: FakeResend) -> None:
    message = EmailMessage("Hi", "<p>rich</p>", "a@samwabluxury.com", ["b@example.com"])
    message.content_subtype = "html"

    backend().send_messages([message])

    assert resend.body()["html"] == "<p>rich</p>"
    assert "text" not in resend.body()


def test_empty_lists_are_left_out(resend: FakeResend) -> None:
    backend().send_messages([EmailMessage("Hi", "x", "a@samwabluxury.com", ["b@example.com"])])

    assert set(resend.body()) == {"from", "to", "subject", "text"}


def test_several_emails_are_several_calls(resend: FakeResend) -> None:
    messages = [EmailMessage("Hi", "x", "a@samwabluxury.com", [f"{n}@example.com"]) for n in "ab"]

    assert backend().send_messages(messages) == 2
    assert [resend.body(n)["to"] for n in (0, 1)] == [["a@example.com"], ["b@example.com"]]


def test_an_email_with_no_recipients_is_skipped(resend: FakeResend) -> None:
    assert backend().send_messages([EmailMessage("Hi", "x", "a@samwabluxury.com", [])]) == 0
    assert resend.requests == []


def test_attachments_are_refused_until_we_need_them(resend: FakeResend) -> None:
    message = EmailMessage("Receipt", "x", "a@samwabluxury.com", ["b@example.com"])
    message.attach("receipt.pdf", b"%PDF", "application/pdf")

    with pytest.raises(ResendError, match="attachments"):
        backend().send_messages([message])
    assert resend.requests == []


@pytest.mark.parametrize("status", [429, 500, 503])
def test_a_busy_or_failing_resend_is_tried_once_more(resend: FakeResend, status: int) -> None:
    resend.replies = [
        (status, {"name": "rate_limit_exceeded", "message": "slow down"}),
        (200, {"id": "x"}),
    ]

    sent = backend().send_messages(
        [EmailMessage("Hi", "x", "a@samwabluxury.com", ["b@example.com"])]
    )

    assert sent == 1
    assert len(resend.requests) == 2


def test_a_second_failure_is_raised_with_resends_reason(resend: FakeResend) -> None:
    resend.replies = [(500, {"name": "application_error", "message": "unexpected"})]

    with pytest.raises(ResendError, match="500 application_error: unexpected"):
        backend().send_messages([EmailMessage("Hi", "x", "a@samwabluxury.com", ["b@example.com"])])
    assert len(resend.requests) == 2


@pytest.mark.parametrize(
    ("status", "name"),
    [(401, "missing_api_key"), (403, "validation_error"), (422, "missing_required_field")],
)
def test_a_request_resend_refuses_is_not_retried(
    resend: FakeResend, status: int, name: str
) -> None:
    resend.replies = [(status, {"name": name, "message": "you can only send testing emails"})]

    with pytest.raises(ResendError, match=f"{status} {name}"):
        backend().send_messages([EmailMessage("Hi", "x", "a@samwabluxury.com", ["b@example.com"])])
    assert len(resend.requests) == 1


def test_an_unreachable_resend_is_a_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def offline(request: Any, timeout: float) -> Any:
        raise urllib.error.URLError("no route")

    monkeypatch.setattr("apps.platform.core.mail.urllib.request.urlopen", offline)
    monkeypatch.setattr("apps.platform.core.mail.time.sleep", lambda seconds: None)

    with pytest.raises(ResendError, match="could not reach Resend"):
        backend().send_messages([EmailMessage("Hi", "x", "a@samwabluxury.com", ["b@example.com"])])


def test_an_error_reply_that_is_not_json_still_reads_clearly(
    resend: FakeResend, monkeypatch: pytest.MonkeyPatch
) -> None:
    def html_error(request: Any, timeout: float) -> Any:
        raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", {}, io.BytesIO(b"<html>"))  # type: ignore[arg-type]

    monkeypatch.setattr("apps.platform.core.mail.urllib.request.urlopen", html_error)

    with pytest.raises(ResendError, match="403 Forbidden"):
        backend().send_messages([EmailMessage("Hi", "x", "a@samwabluxury.com", ["b@example.com"])])


def test_a_key_is_required() -> None:
    with pytest.raises(ResendError, match="RESEND_API_KEY"):
        ResendEmailBackend(api_key="")


def test_it_works_as_a_mailer_from_settings(resend: FakeResend) -> None:
    mailers = {
        "default": {
            "BACKEND": "apps.platform.core.mail.ResendEmailBackend",
            "OPTIONS": {"api_key": "re_made_up_key"},
        }
    }
    with override_settings(MAILERS=mailers):
        sent = mail.send_mail("Hi", "x", "a@samwabluxury.com", ["b@example.com"])

    assert sent == 1
    assert resend.body()["to"] == ["b@example.com"]


# ---------- check_email: prove the key and the sending address work ----------


@override_settings(
    RESEND_API_KEY="re_made_up_key", DEFAULT_FROM_EMAIL="Samwab <no-reply@samwabluxury.com>"
)
def test_check_email_sends_one_test_email(
    resend: FakeResend, capsys: pytest.CaptureFixture[str]
) -> None:
    call_command("check_email", "lead@example.com")

    assert resend.body()["to"] == ["lead@example.com"]
    assert resend.body()["from"] == "Samwab <no-reply@samwabluxury.com>"
    assert "Email is working" in capsys.readouterr().out


@override_settings(RESEND_API_KEY="")
def test_check_email_needs_the_key() -> None:
    with pytest.raises(CommandError, match="RESEND_API_KEY"):
        call_command("check_email", "lead@example.com")


@override_settings(RESEND_API_KEY="re_made_up_key")
def test_check_email_explains_a_refusal(resend: FakeResend) -> None:
    resend.replies = [(403, {"name": "validation_error", "message": "verify a domain"})]

    with pytest.raises(CommandError, match="verify a domain"):
        call_command("check_email", "lead@example.com")
