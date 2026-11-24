"""Tests for the admin screens for capture protocols and comparable sales."""

from typing import Any

import pytest
from django.contrib.admin.sites import site
from django.contrib.messages import get_messages
from django.test import Client, RequestFactory

from apps.inventory.catalog.admin import CaptureShotInline
from apps.inventory.catalog.models import CaptureProtocol, ComparableSale
from apps.inventory.catalog.tests.helpers import (
    make_category,
    make_product_model,
    make_protocol,
    make_sale,
    make_shot,
)
from apps.users.accounts.models import User
from apps.users.accounts.tests.helpers import admin_login

pytestmark = pytest.mark.django_db

ADMIN = "/admin/catalog"


@pytest.fixture
def boss() -> User:
    return User.objects.create_superuser("boss@samwab.com", "correct-horse-9")


@pytest.fixture
def boss_client(client: Client, boss: User) -> Client:
    admin_login(client, boss)
    return client


def page(response: Any) -> str:
    assert response.status_code == 200, response.status_code
    return str(response.content.decode())


def notes(response: Any) -> list[str]:
    return [str(message) for message in get_messages(response.wsgi_request)]


def run_action(client: Client, action: str, protocol: CaptureProtocol) -> Any:
    return client.post(
        f"{ADMIN}/captureprotocol/",
        {"action": action, "_selected_action": [str(protocol.id)]},
        follow=True,
    )


@pytest.mark.parametrize("screen", ["captureprotocol", "comparablesale"])
def test_list_and_add_screens_open(boss_client: Client, screen: str) -> None:
    page(boss_client.get(f"{ADMIN}/{screen}/"))
    page(boss_client.get(f"{ADMIN}/{screen}/add/"))


def test_change_screens_open(boss_client: Client) -> None:
    protocol = make_protocol()
    make_shot(protocol)
    sale = make_sale(category=protocol.category)

    assert "heat_stamp" in page(boss_client.get(f"{ADMIN}/captureprotocol/{protocol.id}/change/"))
    page(boss_client.get(f"{ADMIN}/comparablesale/{sale.id}/change/"))


def test_adding_a_protocol_numbers_it_and_starts_it_as_a_draft(boss_client: Client) -> None:
    bags = make_category("Bags")
    make_protocol(category=bags, version=1, status="active")

    response = boss_client.post(
        f"{ADMIN}/captureprotocol/add/",
        {
            "category": str(bags.id),
            "shots-TOTAL_FORMS": "0",
            "shots-INITIAL_FORMS": "0",
        },
    )

    assert response.status_code == 302
    newest = CaptureProtocol.objects.get(version=2)
    assert (newest.category, newest.status) == (bags, "draft")


def test_staff_add_shots_to_a_draft(boss_client: Client) -> None:
    protocol = make_protocol()

    response = boss_client.post(
        f"{ADMIN}/captureprotocol/{protocol.id}/change/",
        {
            "shots-TOTAL_FORMS": "1",
            "shots-INITIAL_FORMS": "0",
            "shots-0-code": "heat_stamp",
            "shots-0-name": "Heat stamp",
            "shots-0-kind": "photo",
            "shots-0-instrument": "macro_lens",
            "shots-0-magnification": "10",
            "shots-0-is_required": "on",
            "shots-0-sort_order": "1",
        },
    )

    assert response.status_code == 302
    assert list(protocol.shots.values_list("code", "magnification")) == [("heat_stamp", 10)]


def test_shots_are_locked_once_a_protocol_is_active(boss: User) -> None:
    inline = CaptureShotInline(CaptureProtocol, site)
    request = RequestFactory().get("/")
    request.user = boss
    draft = make_protocol(version=1)
    active = make_protocol(category=draft.category, version=2, status="active")

    assert inline.has_add_permission(request, draft) is True
    assert inline.has_change_permission(request, draft) is True
    assert inline.has_delete_permission(request, draft) is True
    assert inline.has_add_permission(request, active) is False
    assert inline.has_change_permission(request, active) is False
    assert inline.has_delete_permission(request, active) is False
    assert inline.has_view_permission(request, active) is True


def test_activate_from_the_list(boss_client: Client) -> None:
    protocol = make_protocol()
    make_shot(protocol)

    response = run_action(boss_client, "activate_selected", protocol)

    protocol.refresh_from_db()
    assert protocol.status == "active"
    assert notes(response) == ["Activated Bags (default) v1."]


def test_a_refused_activation_explains_why(boss_client: Client) -> None:
    protocol = make_protocol()

    response = run_action(boss_client, "activate_selected", protocol)

    protocol.refresh_from_db()
    assert protocol.status == "draft"
    assert notes(response) == [
        "Bags (default) v1: A protocol needs at least one required shot before it is used."
    ]


def test_retire_from_the_list(boss_client: Client) -> None:
    protocol = make_protocol(status="active")

    response = run_action(boss_client, "retire_selected", protocol)

    protocol.refresh_from_db()
    assert protocol.status == "retired"
    assert notes(response) == ["Retired Bags (default) v1."]


def test_new_draft_from_the_list(boss_client: Client) -> None:
    protocol = make_protocol(status="active")
    make_shot(protocol)

    response = run_action(boss_client, "new_draft_selected", protocol)

    draft = CaptureProtocol.objects.get(version=2)
    assert draft.shots.count() == 1
    assert notes(response) == ["Made Bags (default) v2, draft."]


def test_only_a_draft_can_be_deleted(boss_client: Client) -> None:
    draft = make_protocol(version=1)
    active = make_protocol(category=draft.category, version=2, status="active")

    assert boss_client.get(f"{ADMIN}/captureprotocol/{active.id}/delete/").status_code == 403
    response = boss_client.post(f"{ADMIN}/captureprotocol/{draft.id}/delete/", {"post": "yes"})

    assert response.status_code == 302
    assert list(CaptureProtocol.objects.all()) == [active]


def test_staff_record_a_comparable_sale(boss_client: Client) -> None:
    kelly = make_product_model("Kelly 28")

    response = boss_client.post(
        f"{ADMIN}/comparablesale/add/",
        {
            "brand": str(kelly.brand_id),
            "category": str(kelly.category_id),
            "product_model": str(kelly.id),
            "source": "auction",
            "source_url": "https://example.com/lot/42",
            "price_minor": "1420000",
            "currency": "USD",
            "sold_on": "2026-10-01",
        },
    )

    assert response.status_code == 302
    sale = ComparableSale.objects.get()
    assert (sale.product_model, sale.price_minor) == (kelly, 1_420_000)


def test_the_sales_list_shows_prices_in_dollars(boss_client: Client) -> None:
    make_sale(1_420_000)

    assert "14200.00 USD" in page(boss_client.get(f"{ADMIN}/comparablesale/"))
