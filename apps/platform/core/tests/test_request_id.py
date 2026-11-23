"""Tests for apps.platform.core.request_id and apps.platform.core.logs."""

import json
import logging
import sys
import uuid

import pytest
from django.http import HttpRequest, HttpResponse
from django.test import Client, RequestFactory

from apps.platform.core.logs import JsonFormatter, RequestIdFilter
from apps.platform.core.request_id import (
    NO_REQUEST_ID,
    REQUEST_ID_HEADER,
    RequestIdMiddleware,
    get_request_id,
)

HEALTH_URL = "/api/v1/health/"


def make_record(message: str = "hello") -> logging.LogRecord:
    return logging.LogRecord("samwab.test", logging.INFO, __file__, 1, message, None, None)


# ---------- the header ----------


def test_every_response_gets_a_request_id(client: Client) -> None:
    response = client.get(HEALTH_URL)

    request_id = response[REQUEST_ID_HEADER]
    assert uuid.UUID(hex=request_id).version == 7


def test_two_requests_get_different_ids(client: Client) -> None:
    first = client.get(HEALTH_URL)[REQUEST_ID_HEADER]
    second = client.get(HEALTH_URL)[REQUEST_ID_HEADER]

    assert first != second


@pytest.mark.parametrize(
    "sent", ["abc-12345", "frontend.req_0001", "A" * 64, "0193a1b2c3d4e5f60718293a4b5c6d7e"]
)
def test_a_safe_id_from_the_caller_is_kept(client: Client, sent: str) -> None:
    response = client.get(HEALTH_URL, headers={REQUEST_ID_HEADER: sent})

    assert response[REQUEST_ID_HEADER] == sent


@pytest.mark.parametrize(
    "sent",
    [
        "short",  # under 8 characters
        "A" * 65,  # too long
        "has space in it",
        "line\nbreak-attack",
        "<script>alert(1)</script>",
        "ọmọ-ìyá-request",
        "",
    ],
)
def test_an_unsafe_id_from_the_caller_is_replaced(client: Client, sent: str) -> None:
    response = client.get(HEALTH_URL, headers={REQUEST_ID_HEADER: sent})

    request_id = response[REQUEST_ID_HEADER]
    assert request_id != sent
    assert uuid.UUID(hex=request_id).version == 7


def test_error_responses_also_carry_the_id(client: Client) -> None:
    response = client.post(HEALTH_URL)

    assert response.status_code == 405
    assert response.json()["request_id"] == response[REQUEST_ID_HEADER]


# ---------- reading the id in code ----------


def test_no_request_id_outside_a_request() -> None:
    assert get_request_id() == NO_REQUEST_ID


def test_id_is_readable_during_the_request_and_cleared_after() -> None:
    seen: list[str] = []

    def view(request: HttpRequest) -> HttpResponse:
        seen.append(get_request_id())
        return HttpResponse("ok")

    request = RequestFactory().get("/", headers={REQUEST_ID_HEADER: "abc-12345"})
    response = RequestIdMiddleware(view)(request)

    assert seen == ["abc-12345"]
    assert response[REQUEST_ID_HEADER] == "abc-12345"
    assert get_request_id() == NO_REQUEST_ID


def test_id_is_cleared_even_when_the_view_crashes() -> None:
    def view(request: HttpRequest) -> HttpResponse:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        RequestIdMiddleware(view)(RequestFactory().get("/"))

    assert get_request_id() == NO_REQUEST_ID


# ---------- logs ----------


def test_filter_adds_the_request_id_and_never_hides_a_record() -> None:
    record = make_record()

    kept = RequestIdFilter().filter(record)

    assert kept is True
    assert record.request_id == NO_REQUEST_ID  # type: ignore[attr-defined]


def test_filter_uses_the_id_of_the_current_request() -> None:
    records: list[logging.LogRecord] = []

    def view(request: HttpRequest) -> HttpResponse:
        record = make_record()
        RequestIdFilter().filter(record)
        records.append(record)
        return HttpResponse("ok")

    RequestIdMiddleware(view)(RequestFactory().get("/", headers={REQUEST_ID_HEADER: "abc-12345"}))

    assert records[0].request_id == "abc-12345"  # type: ignore[attr-defined]


class Capture(logging.Handler):
    """Collects log records, with the request ID filter applied as in real logging."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []
        self.addFilter(RequestIdFilter())

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def test_djangos_own_warning_for_a_refused_request_has_the_id(client: Client) -> None:
    capture = Capture()
    django_logger = logging.getLogger("django.request")
    django_logger.addHandler(capture)
    try:
        client.post(HEALTH_URL, headers={REQUEST_ID_HEADER: "abc-12345"})
    finally:
        django_logger.removeHandler(capture)

    assert [record.getMessage() for record in capture.records] == [
        "Method Not Allowed: /api/v1/health/"
    ]
    assert capture.records[0].request_id == "abc-12345"  # type: ignore[attr-defined]


@pytest.mark.urls("apps.platform.core.tests.urls_errors")
def test_the_log_line_for_a_crash_has_the_id_and_the_cause() -> None:
    capture = Capture()
    django_logger = logging.getLogger("django.request")
    django_logger.addHandler(capture)
    try:
        response = Client(raise_request_exception=False).get(
            "/api/v1/crash/", headers={REQUEST_ID_HEADER: "abc-12345"}
        )
    finally:
        django_logger.removeHandler(capture)

    assert response.status_code == 500
    assert len(capture.records) == 1
    record = capture.records[0]
    assert record.request_id == "abc-12345"  # type: ignore[attr-defined]
    # The cause is in the log (for us), though never in the response (for the caller).
    assert "secret-database-password" in JsonFormatter().format(record)


def test_json_formatter_writes_one_line_of_json() -> None:
    record = make_record('user said "hi"\nsecond line')
    RequestIdFilter().filter(record)

    line = JsonFormatter().format(record)

    assert "\n" not in line
    entry = json.loads(line)
    assert entry["level"] == "INFO"
    assert entry["logger"] == "samwab.test"
    assert entry["message"] == 'user said "hi"\nsecond line'
    assert entry["request_id"] == NO_REQUEST_ID
    assert entry["time"].endswith("+00:00")
    assert "exception" not in entry


def test_json_formatter_fills_in_message_arguments() -> None:
    record = logging.LogRecord(
        "samwab.test", logging.WARNING, __file__, 1, "order %s failed", ("A-1",), None
    )

    entry = json.loads(JsonFormatter().format(record))

    assert entry["message"] == "order A-1 failed"
    assert entry["level"] == "WARNING"


def test_json_formatter_includes_the_error_when_there_is_one() -> None:
    try:
        raise ValueError("bad value")
    except ValueError:
        record = logging.LogRecord(
            "samwab.test", logging.ERROR, __file__, 1, "failed", None, sys.exc_info()
        )

    entry = json.loads(JsonFormatter().format(record))

    assert "ValueError: bad value" in entry["exception"]


def test_json_formatter_works_without_the_filter() -> None:
    entry = json.loads(JsonFormatter().format(make_record()))

    assert entry["request_id"] == NO_REQUEST_ID
