"""Tests for the one error format (apps/platform/core/api/errors.py).

Each test calls a small view from urls_errors.py that fails in one known way,
then checks the response the front end would receive.
"""

from typing import Any

import pytest
from django.test import Client

import configurations.urls
from apps.platform.core.request_id import REQUEST_ID_HEADER

pytestmark = pytest.mark.urls("apps.platform.core.tests.urls_errors")

PROBLEM = "application/problem+json"
VALID_ORDER: dict[str, Any] = {
    "email": "buyer@example.com",
    "address": {"city": "Lagos"},
    "lines": [{"price": 100}],
}


def problem(response: Any, status: int, code: str) -> dict[str, Any]:
    """Check the parts every error shares, then return the body for more checks."""
    assert response.status_code == status
    assert response["Content-Type"] == PROBLEM
    body: dict[str, Any] = response.json()
    assert body["type"] == "about:blank"
    assert body["status"] == status
    assert body["code"] == code
    assert isinstance(body["title"], str) and body["title"]
    assert isinstance(body["detail"], str) and body["detail"]
    assert body["request_id"] == response[REQUEST_ID_HEADER]
    assert body["instance"] == response.request["PATH_INFO"]
    return body


def post_json(client: Client, path: str, data: Any) -> Any:
    return client.post(path, data=data, content_type="application/json")


# ---------- validation ----------


def test_valid_input_is_not_an_error(client: Client) -> None:
    response = post_json(client, "/api/v1/validate/", VALID_ORDER)

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_missing_fields_are_listed_one_by_one(client: Client) -> None:
    body = problem(post_json(client, "/api/v1/validate/", {}), 400, "validation_error")

    assert body["title"] == "Bad Request"
    assert {"field": "email", "code": "required", "message": "Please fill this in."} in body[
        "errors"
    ]
    assert {error["field"] for error in body["errors"]} == {"email", "address", "lines"}


def test_nested_field_uses_a_dotted_name(client: Client) -> None:
    data = {**VALID_ORDER, "address": {}}

    body = problem(post_json(client, "/api/v1/validate/", data), 400, "validation_error")

    assert [error["field"] for error in body["errors"]] == ["address.city"]


def test_item_in_a_list_keeps_its_position(client: Client) -> None:
    data = {**VALID_ORDER, "lines": [{"price": 100}, {"price": 0}, {}]}

    body = problem(post_json(client, "/api/v1/validate/", data), 400, "validation_error")

    assert [(error["field"], error["code"]) for error in body["errors"]] == [
        ("lines.1.price", "min_value"),
        ("lines.2.price", "required"),
    ]


def test_top_level_list_keeps_each_position(client: Client) -> None:
    body = problem(
        post_json(client, "/api/v1/many/", [{"price": 5}, {"price": 0}]), 400, "validation_error"
    )

    assert [error["field"] for error in body["errors"]] == ["1.price"]


def test_error_about_the_whole_request_has_no_field(client: Client) -> None:
    data = {**VALID_ORDER, "email": "blocked@example.com"}

    body = problem(post_json(client, "/api/v1/validate/", data), 400, "validation_error")

    assert body["errors"] == [
        {"field": None, "code": "blocked", "message": "This order cannot be placed."}
    ]


def test_wrong_type_is_reported(client: Client) -> None:
    data = {**VALID_ORDER, "lines": [{"price": "abc"}]}

    body = problem(post_json(client, "/api/v1/validate/", data), 400, "validation_error")

    assert [(error["field"], error["code"]) for error in body["errors"]] == [
        ("lines.0.price", "invalid")
    ]


def test_non_english_text_survives(client: Client) -> None:
    data = {**VALID_ORDER, "email": "ọmọ-ìyá"}

    body = problem(post_json(client, "/api/v1/validate/", data), 400, "validation_error")

    assert body["errors"][0]["field"] == "email"


def test_body_that_is_not_json_is_a_parse_error(client: Client) -> None:
    response = client.post("/api/v1/validate/", data="{not json", content_type="application/json")

    body = problem(response, 400, "parse_error")
    assert "errors" not in body


def test_wrong_content_type_is_refused(client: Client) -> None:
    response = client.post("/api/v1/validate/", data="email=a", content_type="text/plain")

    problem(response, 415, "unsupported_media_type")


# ---------- login and permission ----------


def test_not_logged_in_is_401_not_403(client: Client) -> None:
    body = problem(client.get("/api/v1/private/"), 401, "not_authenticated")

    assert body["title"] == "Unauthorized"
    assert "errors" not in body


def test_drf_permission_denied_is_403(client: Client) -> None:
    problem(client.get("/api/v1/drf-forbidden/"), 403, "permission_denied")


def test_django_permission_denied_is_403(client: Client) -> None:
    problem(client.get("/api/v1/django-forbidden/"), 403, "permission_denied")


# ---------- not found and wrong method ----------


def test_django_http404_inside_a_view(client: Client) -> None:
    problem(client.get("/api/v1/django-missing/"), 404, "not_found")


def test_unknown_api_path_is_json(client: Client) -> None:
    problem(client.get("/api/v1/no-such-endpoint/"), 404, "not_found")


def test_unknown_path_outside_the_api_is_a_normal_page(client: Client) -> None:
    response = client.get("/no-such-page/")

    assert response.status_code == 404
    assert response["Content-Type"].startswith("text/html")


def test_wrong_method_is_405(client: Client) -> None:
    body = problem(client.delete("/api/v1/validate/"), 405, "method_not_allowed")

    assert "DELETE" in body["detail"]


# ---------- slowing down ----------


def test_too_many_requests_keeps_the_retry_after_header(client: Client) -> None:
    response = client.get("/api/v1/throttled/")

    problem(response, 429, "throttled")
    assert response["Retry-After"] == "30"


# ---------- business errors raised by services ----------


@pytest.mark.parametrize(
    ("path", "status", "code"),
    [
        ("/api/v1/conflict/", 409, "conflict"),
        ("/api/v1/app-not-found/", 404, "not_found"),
        ("/api/v1/app-forbidden/", 403, "permission_denied"),
        ("/api/v1/custom-app-error/", 422, "bid_too_low"),
        ("/api/v1/custom-message/", 422, "date_too_early"),
    ],
)
def test_app_errors_become_problems(client: Client, path: str, status: int, code: str) -> None:
    problem(client.get(path), status, code)


def test_app_error_message_reaches_the_caller(client: Client) -> None:
    assert client.get("/api/v1/custom-app-error/").json()["detail"] == (
        "The bid is below the lowest amount allowed."
    )
    assert client.get("/api/v1/custom-message/").json()["detail"] == "Pick a later date."


# ---------- crashes ----------


def test_crash_in_the_api_is_a_json_500_that_hides_the_cause() -> None:
    client = Client(raise_request_exception=False)

    response = client.get("/api/v1/crash/")

    body = problem(response, 500, "server_error")
    assert "secret-database-password" not in response.content.decode()
    assert "RuntimeError" not in response.content.decode()
    assert "errors" not in body


def test_crash_outside_the_api_is_a_normal_page_that_hides_the_cause() -> None:
    client = Client(raise_request_exception=False)

    response = client.get("/pages/crash/")

    assert response.status_code == 500
    assert response["Content-Type"].startswith("text/html")
    assert "secret-database-password" not in response.content.decode()


# ---------- wiring ----------


def test_the_real_project_uses_these_handlers() -> None:
    assert configurations.urls.handler404 == "apps.platform.core.api.errors.page_not_found"
    assert configurations.urls.handler500 == "apps.platform.core.api.errors.server_error"


# ---------- CSRF ----------


def test_missing_csrf_token_on_an_api_path_is_a_json_403() -> None:
    client = Client(enforce_csrf_checks=True)

    body = problem(client.post("/api/v1/plain-form/"), 403, "csrf_failed")

    assert "errors" not in body


def test_missing_csrf_token_outside_the_api_is_a_normal_page() -> None:
    client = Client(enforce_csrf_checks=True)

    response = client.post("/pages/plain-form/")

    assert response.status_code == 403
    assert response["Content-Type"].startswith("text/html")


def test_a_valid_csrf_token_is_accepted() -> None:
    client = Client(enforce_csrf_checks=True)
    token = client.get("/api/v1/plain-form/").cookies["csrftoken"].value

    response = client.post("/api/v1/plain-form/", headers={"X-CSRFToken": token})

    assert response.status_code == 200


def test_the_project_uses_the_json_csrf_answer() -> None:
    from django.conf import settings

    assert settings.CSRF_FAILURE_VIEW == "apps.platform.core.api.errors.csrf_failure"


# ---------- allauth paths ----------


@pytest.mark.urls("configurations.urls")
def test_unknown_allauth_path_is_json(client: Client) -> None:
    problem(client.get("/_allauth/no-such-endpoint/"), 404, "not_found")
