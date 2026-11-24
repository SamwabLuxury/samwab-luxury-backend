"""Changes staff make to accounts in the admin site, above all roles given or taken, are audited."""

import pytest
from django.contrib.auth.models import Group
from django.test import Client

from apps.platform.audit.models import AuditEvent
from apps.users.accounts.models import User
from apps.users.accounts.tests.helpers import admin_login

pytestmark = pytest.mark.django_db

PASSWORD = "correct-horse-battery-staple"  # noqa: S105
USERS = "/admin/accounts/user"


@pytest.fixture
def boss() -> User:
    return User.objects.create_superuser("boss@example.com", PASSWORD)


@pytest.fixture
def boss_client(client: Client, boss: User) -> Client:
    admin_login(client, boss)
    return client


def details(**extra: object) -> dict[str, object]:
    values: dict[str, object] = {
        "email": "ada@example.com",
        "first_name": "",
        "last_name": "",
        "country": "",
        "locale": "en",
        "timezone": "UTC",
        "is_active": "on",
        "verification_tier": "0",
    }
    values.update(extra)
    return values


def test_giving_a_role_records_who_gave_it(boss_client: Client, boss: User) -> None:
    ada = User.objects.create_user("ada@example.com", PASSWORD)
    editor = Group.objects.get(name="catalog_editor")

    response = boss_client.post(
        f"{USERS}/{ada.pk}/change/", details(is_staff="on", groups=[str(editor.pk)])
    )

    assert response.status_code == 302
    event = AuditEvent.objects.get()
    assert (event.action, event.object_id, event.actor) == ("accounts.user.changed", ada.id, boss)
    assert event.changes == {
        "is_staff": {"from": False, "to": True},
        "groups": {"from": [], "to": ["catalog_editor"]},
    }


def test_taking_a_role_away_is_recorded(boss_client: Client) -> None:
    ada = User.objects.create_user("ada@example.com", PASSWORD)
    ada.groups.add(Group.objects.get(name="reviewer"))

    boss_client.post(f"{USERS}/{ada.pk}/change/", details())

    assert AuditEvent.objects.get().changes == {"groups": {"from": ["reviewer"], "to": []}}


def test_saving_without_a_change_records_nothing(boss_client: Client) -> None:
    ada = User.objects.create_user("ada@example.com", PASSWORD)

    boss_client.post(f"{USERS}/{ada.pk}/change/", details())

    assert not AuditEvent.objects.exists()


def test_adding_a_person_is_recorded_without_the_password(boss_client: Client) -> None:
    response = boss_client.post(
        f"{USERS}/add/",
        {
            "email": "new@example.com",
            "usable_password": "true",
            "password1": PASSWORD,
            "password2": PASSWORD,
        },
    )

    assert response.status_code == 302
    event = AuditEvent.objects.get()
    assert event.action == "accounts.user.created"
    assert event.changes["email"] == {"to": "new@example.com"}
    assert "password" not in event.changes
    assert PASSWORD not in str(event.changes)
