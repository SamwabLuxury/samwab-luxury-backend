"""Tests for the audit log screen: staff can read it, nobody can change it."""

from typing import Any

import pytest
from django.contrib.auth.models import Permission
from django.test import Client

from apps.platform.audit.models import AuditEvent
from apps.users.accounts.models import User
from apps.users.accounts.tests.helpers import admin_login, make_staff

pytestmark = pytest.mark.django_db

ADMIN = "/admin/audit/auditevent"


@pytest.fixture
def boss() -> User:
    return User.objects.create_superuser("boss@samwab.com", "correct-horse-9")


@pytest.fixture
def event(boss: User) -> AuditEvent:
    return AuditEvent.objects.create(
        actor=boss,
        action="catalog.brand.created",
        object_type="catalog.brand",
        changes={"name": {"to": "Hermès"}},
        request_id="req-12345678",
    )


def page(response: Any) -> str:
    assert response.status_code == 200, response.status_code
    return str(response.content.decode())


def test_the_list_shows_and_searches_events(client: Client, boss: User, event: AuditEvent) -> None:
    admin_login(client, boss)

    html = page(client.get(f"{ADMIN}/", {"q": "req-12345678"}))

    assert "catalog.brand.created" in html
    assert "boss@samwab.com" in html


def test_an_event_opens_read_only(client: Client, boss: User, event: AuditEvent) -> None:
    admin_login(client, boss)

    html = page(client.get(f"{ADMIN}/{event.id}/change/"))

    assert "Hermès" in html
    assert 'name="action"' not in html
    assert 'name="_save"' not in html


def test_even_a_superuser_cannot_add_change_or_delete(
    client: Client, boss: User, event: AuditEvent
) -> None:
    admin_login(client, boss)

    assert client.get(f"{ADMIN}/add/").status_code == 403
    assert client.post(f"{ADMIN}/{event.id}/change/", {"action": "x"}).status_code == 403
    assert client.get(f"{ADMIN}/{event.id}/delete/").status_code == 403
    assert "delete_selected" not in page(client.get(f"{ADMIN}/"))
    event.refresh_from_db()
    assert event.action == "catalog.brand.created"


def test_staff_need_the_view_permission(client: Client, event: AuditEvent) -> None:
    clerk = make_staff("clerk@samwab.com")
    admin_login(client, clerk)
    assert client.get(f"{ADMIN}/").status_code == 403

    clerk.user_permissions.add(Permission.objects.get(codename="view_auditevent"))
    assert "catalog.brand.created" in page(client.get(f"{ADMIN}/"))
