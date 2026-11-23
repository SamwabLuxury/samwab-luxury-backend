"""Tests for apps.platform.core.client_ip: the caller's IP address, kept for the audit log."""

import pytest
from django.http import HttpRequest, HttpResponse
from django.test import RequestFactory

from apps.platform.core.client_ip import ClientIpMiddleware, get_client_ip


def run(remote_addr: str) -> str | None:
    seen: list[str | None] = []

    def view(request: HttpRequest) -> HttpResponse:
        seen.append(get_client_ip())
        return HttpResponse()

    ClientIpMiddleware(view)(RequestFactory().get("/", REMOTE_ADDR=remote_addr))
    return seen[0]


def test_outside_a_request_there_is_no_ip() -> None:
    assert get_client_ip() is None


@pytest.mark.parametrize("address", ["127.0.0.1", "203.0.113.9", "2001:db8::1"])
def test_the_address_of_the_caller_is_kept_during_the_request(address: str) -> None:
    assert run(address) == address


@pytest.mark.parametrize("address", ["", "not-an-ip", "10.0.0.1, 10.0.0.2"])
def test_anything_that_is_not_one_ip_address_is_ignored(address: str) -> None:
    assert run(address) is None


def test_the_ip_is_forgotten_when_the_request_ends() -> None:
    run("203.0.113.9")

    assert get_client_ip() is None


def test_a_forwarded_header_is_not_trusted() -> None:
    seen: list[str | None] = []

    def view(request: HttpRequest) -> HttpResponse:
        seen.append(get_client_ip())
        return HttpResponse()

    request = RequestFactory().get("/", REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR="198.51.100.7")
    ClientIpMiddleware(view)(request)

    assert seen == ["10.0.0.1"]
