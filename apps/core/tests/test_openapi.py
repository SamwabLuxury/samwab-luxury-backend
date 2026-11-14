"""Tests for the OpenAPI file and the docs page the front end reads."""

from io import StringIO

from django.core.management import call_command
from django.test import Client
from django.urls import reverse

SCHEMA_URL = "/api/v1/schema/"
DOCS_URL = "/api/v1/docs/"


def test_url_names() -> None:
    assert reverse("core:schema") == SCHEMA_URL
    assert reverse("core:docs") == DOCS_URL


def test_schema_is_open_and_describes_the_health_endpoint(client: Client) -> None:
    response = client.get(SCHEMA_URL, {"format": "json"})

    assert response.status_code == 200
    schema = response.json()
    assert schema["openapi"].startswith("3.")
    assert schema["info"]["title"] == "Samwab API"
    health = schema["paths"]["/api/v1/health/"]["get"]
    assert health["summary"] == "Check that the API is running"
    assert "200" in health["responses"]


def test_schema_does_not_list_itself(client: Client) -> None:
    schema = client.get(SCHEMA_URL, {"format": "json"}).json()

    assert SCHEMA_URL not in schema["paths"]
    assert DOCS_URL not in schema["paths"]


def test_default_schema_format_is_yaml(client: Client) -> None:
    response = client.get(SCHEMA_URL)

    assert response.status_code == 200
    assert response["Content-Type"].startswith("application/vnd.oai.openapi")
    assert response.content.decode().startswith("openapi: 3.")


def test_docs_page_opens_without_login(client: Client) -> None:
    response = client.get(DOCS_URL)

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/html")
    assert SCHEMA_URL in response.content.decode()


def test_schema_builds_with_no_warnings() -> None:
    """The same check CI runs. A view the schema cannot describe fails here."""
    output = StringIO()

    call_command("spectacular", "--validate", "--fail-on-warn", stdout=output)

    assert "/api/v1/health/" in output.getvalue()
