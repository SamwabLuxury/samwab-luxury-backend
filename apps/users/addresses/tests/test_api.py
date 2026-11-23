"""GET and POST /api/v1/me/addresses/: a buyer's own delivery addresses."""

from typing import Any

import pytest
from django.test import Client

from apps.users.accounts.models import User
from apps.users.addresses.models import Address
from apps.users.addresses.tests.helpers import make_address, make_user

pytestmark = pytest.mark.django_db

URL = "/api/v1/me/addresses/"
LEKKI = {
    "label": "Home",
    "recipient_name": "Adaeze Obi",
    "line1": "12 Admiralty Way",
    "line2": "Flat 4",
    "city": "Lagos",
    "region": "Lagos",
    "postal_code": "106104",
    "country": "NG",
    "phone": "+234 803 000 0000",
}


@pytest.fixture
def ada() -> User:
    return make_user()


@pytest.fixture
def ada_client(client: Client, ada: User) -> Client:
    client.force_login(ada)
    return client


def post(client: Client, body: dict[str, Any]) -> Any:
    return client.post(URL, body, content_type="application/json")


def test_adding_an_address_returns_it_in_the_contract_shape(ada_client: Client) -> None:
    response = post(ada_client, LEKKI)

    assert response.status_code == 201, response.content
    body = response.json()
    assert body == {**LEKKI, "id": body["id"], "is_default": True}
    assert Address.objects.get().user.email == "ada@example.com"


def test_only_the_required_parts(ada_client: Client) -> None:
    body = {
        "recipient_name": "Adaeze Obi",
        "line1": "12 Admiralty Way",
        "city": "Lagos",
        "country": "NG",
    }

    response = post(ada_client, body)

    assert response.status_code == 201, response.content
    assert response.json()["line2"] is None
    assert response.json()["phone"] is None
    assert response.json()["label"] == ""


def test_empty_optional_parts_are_stored_as_nothing(ada_client: Client) -> None:
    response = post(ada_client, {**LEKKI, "line2": "", "phone": ""})

    assert (response.json()["line2"], response.json()["phone"]) == (None, None)
    assert Address.objects.filter(**{"line2__isnull": True, "phone__isnull": True}).count() == 1


def test_a_lowercase_country_code_is_accepted(ada_client: Client) -> None:
    response = post(ada_client, {**LEKKI, "country": "us"})

    assert response.json()["country"] == "US"


def test_bad_fields_are_a_400_naming_each_field(ada_client: Client) -> None:
    response = post(
        ada_client, {"line1": "", "city": "Lagos", "country": "Nigeria", "phone": "abc"}
    )

    assert response.status_code == 400
    assert response["Content-Type"] == "application/problem+json"
    fields = {error["field"] for error in response.json()["errors"]}
    assert fields == {"recipient_name", "line1", "country", "phone"}


def test_the_list_shows_only_my_addresses_newest_first(ada_client: Client, ada: User) -> None:
    older = make_address(ada)
    newer = make_address(ada, label="Office")
    make_address(make_user("chidi@example.com"))

    response = ada_client.get(URL)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"next", "previous", "results"}
    assert [row["id"] for row in body["results"]] == [str(newer.pk), str(older.pk)]
    assert body["results"][1]["recipient_name"] == "Adaeze Obi"


def test_the_limit_is_a_422(ada_client: Client, ada: User) -> None:
    from apps.users.addresses.services import MAX_ADDRESSES

    for _ in range(MAX_ADDRESSES):
        make_address(ada)

    response = post(ada_client, LEKKI)

    assert response.status_code == 422
    assert response.json()["code"] == "address_limit_reached"


def test_a_body_that_is_not_an_object_is_a_400(ada_client: Client) -> None:
    response = ada_client.post(URL, [LEKKI], content_type="application/json")

    assert response.status_code == 400


@pytest.mark.parametrize("method", ["get", "post"])
def test_login_is_needed(client: Client, method: str) -> None:
    response = getattr(client, method)(URL)

    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"


def test_a_post_without_the_csrf_token_is_refused(ada: User) -> None:
    client = Client(enforce_csrf_checks=True)
    client.force_login(ada)

    response = post(client, LEKKI)

    assert response.status_code == 403
    assert response.json()["code"] == "csrf_failed"
    assert not Address.objects.exists()
