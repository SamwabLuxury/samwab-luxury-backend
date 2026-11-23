"""Tests for the @idempotent decorator, through a real request to a test endpoint."""

import threading
from typing import Any

import pytest
from django.db import connection
from django.test import Client

from apps.inventory.catalog.models import Material
from apps.platform.idempotency.models import IdempotencyKey
from apps.users.accounts.models import User

pytestmark = [pytest.mark.django_db, pytest.mark.urls("apps.platform.idempotency.tests.urls")]

URL = "/api/v1/test-materials/"
KEY = "8e03978e-40d5-43e8-bc93-6894a57f9324"


@pytest.fixture
def ada_client(client: Client) -> Client:
    client.force_login(User.objects.create_user("ada@example.com", "correct-horse-9"))
    return client


def post(client: Client, body: dict[str, Any], key: str | None = KEY) -> Any:
    headers = {} if key is None else {"Idempotency-Key": key}
    return client.post(URL, body, content_type="application/json", headers=headers)


def test_the_first_request_runs_and_answers_normally(ada_client: Client) -> None:
    response = post(ada_client, {"name": "Togo leather"})

    assert response.status_code == 201
    assert response.json()["name"] == "Togo leather"
    assert "Idempotent-Replayed" not in response
    assert Material.objects.count() == 1


def test_a_retry_gets_the_first_answer_and_nothing_runs_twice(ada_client: Client) -> None:
    first = post(ada_client, {"name": "Togo leather"})

    again = post(ada_client, {"name": "Togo leather"})

    assert again.status_code == 201
    assert again.json() == first.json()
    assert again["Idempotent-Replayed"] == "true"
    assert Material.objects.count() == 1


def test_the_header_is_required(ada_client: Client) -> None:
    response = post(ada_client, {"name": "Togo leather"}, key=None)

    assert response.status_code == 400
    assert response["Content-Type"] == "application/problem+json"
    assert response.json()["code"] == "idempotency_key_missing"
    assert not Material.objects.exists()


@pytest.mark.parametrize("bad", ["", "   ", "x" * 256, "has space", "naïve"])
def test_a_key_must_be_1_to_255_plain_characters(ada_client: Client, bad: str) -> None:
    response = post(ada_client, {"name": "Togo leather"}, key=bad)

    assert response.status_code == 400
    assert response.json()["code"] in {"idempotency_key_missing", "idempotency_key_invalid"}


def test_a_key_of_255_characters_is_accepted(ada_client: Client) -> None:
    assert post(ada_client, {"name": "Togo leather"}, key="k" * 255).status_code == 201


def test_a_quoted_key_is_the_same_key(ada_client: Client) -> None:
    """The standard draft writes the key as a quoted string; Stripe sends it bare."""
    post(ada_client, {"name": "Togo leather"}, key=f'"{KEY}"')

    again = post(ada_client, {"name": "Togo leather"}, key=KEY)

    assert again["Idempotent-Replayed"] == "true"


def test_reusing_a_key_for_another_request_is_refused(ada_client: Client) -> None:
    post(ada_client, {"name": "Togo leather"})

    response = post(ada_client, {"name": "Box calf"})

    assert response.status_code == 422
    assert response.json()["code"] == "idempotency_key_reused"
    assert Material.objects.count() == 1


def test_a_request_still_running_gets_a_conflict(ada_client: Client) -> None:
    post(ada_client, {"name": "Togo leather"}, key="other")
    IdempotencyKey.objects.update(response_status=None, response_body=None)

    response = post(ada_client, {"name": "Togo leather"}, key="other")

    assert response.status_code == 409
    assert response.json()["code"] == "idempotency_key_in_progress"


def test_a_refused_request_frees_its_key(ada_client: Client) -> None:
    refused = post(ada_client, {"name": "refuse"})
    assert refused.status_code == 422
    assert refused.json()["code"] == "too_expensive"
    assert not IdempotencyKey.objects.exists()

    assert post(ada_client, {"name": "refuse"}).json()["code"] == "too_expensive"


def test_a_server_error_frees_its_key(ada_client: Client) -> None:
    assert post(ada_client, {"name": "server-error"}).status_code == 503

    assert not IdempotencyKey.objects.exists()


def test_invalid_input_never_reaches_the_key_store(ada_client: Client) -> None:
    response = ada_client.post(
        URL, "not json", content_type="application/json", headers={"Idempotency-Key": KEY}
    )

    assert response.status_code == 400
    assert not IdempotencyKey.objects.exists()


def test_login_is_checked_before_the_key(client: Client) -> None:
    response = post(client, {"name": "Togo leather"}, key=None)

    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"


def test_an_endpoint_open_to_anyone_still_needs_a_login_for_a_key(client: Client) -> None:
    response = client.post(
        "/api/v1/test-open/", {}, content_type="application/json", headers={"Idempotency-Key": KEY}
    )

    assert response.status_code == 401
    assert not IdempotencyKey.objects.exists()


def test_requests_without_the_decorator_do_not_need_a_key(ada_client: Client) -> None:
    assert ada_client.get(URL).status_code == 200


def test_the_api_description_lists_the_required_header() -> None:
    from drf_spectacular.generators import SchemaGenerator

    from apps.platform.idempotency.tests.urls import urlpatterns

    generator = SchemaGenerator(patterns=urlpatterns)  # type: ignore[no-untyped-call]
    schema = generator.get_schema(request=None, public=True)  # type: ignore[no-untyped-call]
    parameters = schema["paths"][URL]["post"]["parameters"]

    assert {
        "in": "header",
        "name": "Idempotency-Key",
        "required": True,
        "schema": {"type": "string", "maxLength": 255},
        "description": "Repeating a request with the same key returns the first result.",
    } in parameters
    assert "parameters" not in schema["paths"][URL]["get"]


@pytest.mark.skipif(connection.vendor != "postgresql", reason="needs real concurrent connections")
@pytest.mark.django_db(transaction=True)
def test_two_requests_at_once_run_the_work_once() -> None:
    """Two tabs send the same key at the same moment: the work runs once."""
    User.objects.create_user("ada@example.com", "correct-horse-9")
    answers: list[int] = []
    start = threading.Barrier(2)

    def send() -> None:
        client = Client()
        client.force_login(User.objects.get())
        start.wait()
        answers.append(post(client, {"name": "Togo leather"}).status_code)
        connection.close()

    threads = [threading.Thread(target=send) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert Material.objects.count() == 1
    assert sorted(answers) in ([201, 201], [201, 409])
