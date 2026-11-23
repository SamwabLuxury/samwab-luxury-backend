"""Tests for apps.platform.audit.services: how a change becomes an audit event."""

import uuid
from datetime import date

import pytest
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.test import RequestFactory

from apps.inventory.catalog.models import Brand, ComparableSale
from apps.inventory.catalog.tests.helpers import make_brand, make_sale
from apps.platform.audit import services
from apps.platform.audit.models import AuditEvent
from apps.platform.core.client_ip import ClientIpMiddleware
from apps.platform.core.request_id import RequestIdMiddleware
from apps.users.accounts.models import User

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff() -> User:
    return User.objects.create_user("ada@samwab.com", "correct-horse-9")


# ---------- snapshots and differences ----------


def test_a_snapshot_has_the_fields_but_not_the_id_or_timestamps() -> None:
    hermes = make_brand("Hermès")

    assert services.snapshot(hermes) == {"name": "Hermès", "slug": "hermes", "is_active": True}


def test_a_snapshot_shows_related_rows_by_id_and_dates_as_text() -> None:
    sale = make_sale(price_minor=1_000, sold_on=date(2026, 10, 1))

    shot = services.snapshot(sale)

    assert shot["brand_id"] == str(sale.brand_id)
    assert shot["sold_on"] == "2026-10-01"
    assert shot["price_minor"] == 1_000


def test_a_snapshot_records_a_stored_file_by_its_name() -> None:
    from apps.inventory.pieces.models import Media

    media = Media(file="pieces/abc/photo.jpg", kind="listing", sha256="0" * 64, width=1, height=1)

    assert services.snapshot(media)["file"] == "pieces/abc/photo.jpg"
    assert services.snapshot(Media(kind="flaw"))["file"] is None


def test_a_snapshot_can_leave_fields_out() -> None:
    hermes = make_brand("Hermès")

    assert services.snapshot(hermes, exclude={"slug"}) == {"name": "Hermès", "is_active": True}


@pytest.mark.parametrize(
    ("name", "recorded"),
    [
        ("name", True),
        ("brand_id", True),
        ("address_enc", False),  # encrypted columns (build 10) never reach the audit log
        ("id", False),
        ("created_at", False),
        ("updated_at", False),
        ("updated_by_id", False),  # the event's actor already says who
    ],
)
def test_which_columns_a_snapshot_keeps(name: str, recorded: bool) -> None:
    assert services.is_recorded_field(name) is recorded


def test_a_snapshot_can_list_many_to_many_rows_by_name(staff: User) -> None:
    from django.contrib.auth.models import Group

    staff.groups.add(Group.objects.get(name="reviewer"), Group.objects.get(name="admin"))

    shot = services.snapshot(staff, many=("groups",), exclude={"password", "last_login"})

    assert shot["groups"] == ["admin", "reviewer"]
    assert "password" not in shot


def test_the_difference_lists_only_what_changed() -> None:
    before = {"name": "Hermes", "slug": "hermes", "is_active": True}
    after = {"name": "Hermès", "slug": "hermes", "is_active": True}

    assert services.difference(before, after) == {"name": {"from": "Hermes", "to": "Hermès"}}


def test_the_difference_of_a_new_row_has_only_new_values() -> None:
    assert services.difference(None, {"name": "Hermès"}) == {"name": {"to": "Hermès"}}


def test_the_difference_of_a_deleted_row_has_only_old_values() -> None:
    assert services.difference({"name": "Hermès"}, None) == {"name": {"from": "Hermès"}}


def test_no_change_gives_an_empty_difference() -> None:
    assert services.difference({"name": "Hermès"}, {"name": "Hermès"}) == {}


# ---------- recording ----------


def test_record_writes_who_did_what_to_which_row(staff: User) -> None:
    hermes = make_brand("Hermès")

    event = services.record("retired", hermes, by=staff, changes={"is_active": {"to": False}})

    event.refresh_from_db()
    assert event.action == "catalog.brand.retired"
    assert event.object_type == "catalog.brand"
    assert event.object_id == hermes.id
    assert event.actor == staff
    assert event.changes == {"is_active": {"to": False}}


def test_outside_a_request_there_is_no_ip_or_request_id(staff: User) -> None:
    event = services.record("created", make_brand(), by=staff)

    assert (event.ip_address, event.request_id) == (None, None)


def test_inside_a_request_the_ip_and_request_id_are_kept(staff: User) -> None:
    hermes = make_brand()
    seen: list[AuditEvent] = []

    def view(request: HttpRequest) -> HttpResponse:
        seen.append(services.record("created", hermes, by=staff))
        return HttpResponse()

    handler = RequestIdMiddleware(ClientIpMiddleware(view))
    request = RequestFactory().get("/", REMOTE_ADDR="203.0.113.9", HTTP_X_REQUEST_ID="req-12345678")

    handler(request)

    seen[0].refresh_from_db()
    assert seen[0].ip_address == "203.0.113.9"
    assert seen[0].request_id == "req-12345678"


def test_an_event_is_lost_with_the_change_it_describes(staff: User) -> None:
    hermes = make_brand()

    with pytest.raises(RuntimeError), transaction.atomic():
        services.record("created", hermes, by=staff)
        raise RuntimeError("the change failed")

    assert not AuditEvent.objects.exists()


def test_only_rows_with_a_uuid_can_be_recorded(staff: User) -> None:
    from django.contrib.auth.models import Group

    with pytest.raises(TypeError, match="UUID"):
        services.record("changed", Group.objects.first(), by=staff)  # type: ignore[arg-type]


def test_record_saved_writes_created_for_a_new_row(staff: User) -> None:
    hermes = make_brand("Hermès")

    event = services.record_saved(hermes, before=None, by=staff)

    assert event is not None
    assert event.action == "catalog.brand.created"
    assert event.changes["name"] == {"to": "Hermès"}


def test_record_saved_writes_changed_with_the_difference(staff: User) -> None:
    hermes = make_brand("Hermes")
    before = services.snapshot(hermes)
    Brand.objects.filter(pk=hermes.pk).update(name="Hermès")
    hermes.refresh_from_db()

    event = services.record_saved(hermes, before=before, by=staff)

    assert event is not None
    assert event.action == "catalog.brand.changed"
    assert event.changes == {"name": {"from": "Hermes", "to": "Hermès"}}


def test_record_saved_writes_nothing_when_nothing_changed(staff: User) -> None:
    hermes = make_brand()

    assert services.record_saved(hermes, before=services.snapshot(hermes), by=staff) is None
    assert not AuditEvent.objects.exists()


def test_record_deleted_keeps_the_old_values(staff: User) -> None:
    sale = make_sale(price_minor=5_000)
    sale_id = sale.id
    before = services.snapshot(sale)
    sale.delete()

    event = services.record_deleted(ComparableSale, sale_id, before=before, by=staff)

    assert event.action == "catalog.comparablesale.deleted"
    assert event.object_id == sale_id
    assert event.changes["price_minor"] == {"from": 5_000}


def test_the_stored_object_id_is_a_uuid(staff: User) -> None:
    event = services.record("created", make_brand(), by=staff)

    assert isinstance(AuditEvent.objects.get(pk=event.pk).object_id, uuid.UUID)
