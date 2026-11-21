"""Tests for the audit_events table: it only ever grows."""

import uuid

import pytest
from django.db import connection, transaction
from django.db.models import ProtectedError
from django.db.utils import IntegrityError

from apps.accounts.models import User
from apps.audit.models import AuditEvent, AuditEventIsFinalError

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff() -> User:
    return User.objects.create_user("ada@samwab.com", "correct-horse-9")


def make_event(**fields: object) -> AuditEvent:
    fields.setdefault("action", "catalog.brand.created")
    fields.setdefault("object_type", "catalog.brand")
    return AuditEvent.objects.create(**fields)


def test_an_event_gets_its_id_time_and_empty_changes() -> None:
    event = make_event()

    event.refresh_from_db()
    assert uuid.UUID(str(event.id)).version == 7
    assert event.changes == {}
    assert event.occurred_at is not None
    assert (event.actor, event.object_id, event.ip_address, event.request_id) == (
        None,
        None,
        None,
        None,
    )


def test_the_table_name_follows_the_data_model() -> None:
    assert AuditEvent._meta.db_table == "audit_events"


def test_the_newest_event_comes_first() -> None:
    first = make_event()
    second = make_event()

    assert list(AuditEvent.objects.all()) == [second, first]


def test_an_ipv6_address_is_stored_in_its_short_form() -> None:
    event = make_event(ip_address="2001:0db8:0000:0000:0000:0000:0000:0001")

    event.refresh_from_db()
    assert event.ip_address == "2001:db8::1"


def test_a_saved_event_cannot_be_changed() -> None:
    event = make_event()
    event.action = "catalog.brand.deleted"

    with pytest.raises(AuditEventIsFinalError):
        event.save()


def test_a_saved_event_cannot_be_deleted() -> None:
    event = make_event()

    with pytest.raises(AuditEventIsFinalError):
        event.delete()


def test_events_cannot_be_changed_or_deleted_in_bulk() -> None:
    make_event()

    with pytest.raises(AuditEventIsFinalError):
        AuditEvent.objects.update(action="changed")
    with pytest.raises(AuditEventIsFinalError):
        AuditEvent.objects.all().delete()
    assert AuditEvent.objects.get().action == "catalog.brand.created"


def test_a_person_with_audit_history_cannot_be_deleted(staff: User) -> None:
    make_event(actor=staff)

    with pytest.raises(ProtectedError):
        staff.delete()


@pytest.mark.skipif(connection.vendor != "postgresql", reason="the trigger exists on PostgreSQL")
@pytest.mark.parametrize(
    "sql",
    ["UPDATE audit_events SET action = 'changed'", "DELETE FROM audit_events"],
)
def test_the_database_refuses_changes_that_skip_django(sql: str) -> None:
    make_event()

    with pytest.raises(IntegrityError, match="append-only"):  # noqa: SIM117
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(sql)
    assert AuditEvent.objects.get().action == "catalog.brand.created"
