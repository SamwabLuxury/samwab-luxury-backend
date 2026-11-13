"""Tests for GET /api/v1/health/.

pytest-django blocks database access unless a test asks for it, so these
tests also prove the endpoint works without a database.
"""

import pytest
from django.conf import settings
from django.test import Client
from django.urls import reverse

HEALTH_URL = "/api/v1/health/"


def test_url_name_points_to_health_path() -> None:
    assert reverse("core:health") == HEALTH_URL


def test_anonymous_user_gets_ok(client: Client) -> None:
    response = client.get(HEALTH_URL)

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_response_is_json(client: Client) -> None:
    response = client.get(HEALTH_URL)

    assert response["Content-Type"] == "application/json"


def test_query_string_is_ignored(client: Client) -> None:
    response = client.get(HEALTH_URL, {"anything": "x" * 500})

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_other_methods_are_not_allowed(client: Client, method: str) -> None:
    response = getattr(client, method)(HEALTH_URL)

    assert response.status_code == 405


def test_missing_trailing_slash_redirects_to_health(client: Client) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 301
    assert response["Location"] == HEALTH_URL


def test_unknown_api_path_returns_404(client: Client) -> None:
    response = client.get("/api/v1/does-not-exist/")

    assert response.status_code == 404


def test_api_requires_login_by_default() -> None:
    """Health opts out on purpose. Every other endpoint must stay private by default."""
    assert settings.REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"] == [
        "rest_framework.permissions.IsAuthenticated"
    ]


def test_debug_is_off_in_tests() -> None:
    assert settings.DEBUG is False
