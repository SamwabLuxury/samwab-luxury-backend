"""Every staff change to the catalog leaves one audit event, written with the change."""

from typing import Any

import pytest
from django.test import Client

from apps.inventory.catalog import services
from apps.inventory.catalog.exceptions import ProtocolNotDraftError
from apps.inventory.catalog.models import Brand, CaptureProtocol, Category, ComparableSale, Material
from apps.inventory.catalog.tests.helpers import (
    make_brand,
    make_category,
    make_material,
    make_protocol,
    make_sale,
    make_shot,
)
from apps.platform.audit.models import AuditEvent
from apps.platform.core.request_id import REQUEST_ID_HEADER
from apps.users.accounts.models import User
from apps.users.accounts.tests.helpers import admin_login, make_staff

pytestmark = pytest.mark.django_db

ADMIN = "/admin/catalog"


@pytest.fixture
def editor() -> User:
    user: User = make_staff("ed@samwab.com", "catalog_editor")
    return user


@pytest.fixture
def editor_client(client: Client, editor: User) -> Client:
    admin_login(client, editor)
    return client


def actions() -> list[str]:
    return list(AuditEvent.objects.order_by("id").values_list("action", flat=True))


def only_event() -> AuditEvent:
    return AuditEvent.objects.get()


# ---------- save_entry ----------


def test_adding_an_entry_records_its_values(editor: User) -> None:
    services.save_entry(Brand(name="Hermès", slug="hermes"), by=editor)

    event = only_event()
    assert event.action == "catalog.brand.created"
    assert event.actor == editor
    assert event.object_id == Brand.objects.get().id
    assert event.changes == {
        "name": {"to": "Hermès"},
        "slug": {"to": "hermes"},
        "is_active": {"to": True},
    }


def test_changing_an_entry_records_only_what_changed(editor: User) -> None:
    hermes = make_brand("Hermes")
    hermes.name = "Hermès"

    services.save_entry(hermes, by=editor)

    assert only_event().changes == {"name": {"from": "Hermes", "to": "Hermès"}}


def test_a_category_change_does_not_record_its_own_editor_column(editor: User) -> None:
    bags = make_category("Bags")
    bags.sort_order = 3

    services.save_entry(bags, by=editor)

    assert only_event().changes == {"sort_order": {"from": 0, "to": 3}}


def test_saving_without_a_change_records_nothing(editor: User) -> None:
    services.save_entry(make_brand(), by=editor)

    assert not AuditEvent.objects.exists()


def test_a_refused_entry_records_nothing(editor: User) -> None:
    with pytest.raises(Exception, match="slug"):
        services.save_entry(Brand(name="Hermès", slug="Not A Slug"), by=editor)

    assert not AuditEvent.objects.exists()


# ---------- retire and bring back ----------


def test_retiring_records_one_event_per_row_that_changed(editor: User) -> None:
    hermes = make_brand("Hermès")
    make_brand("Chanel", is_active=False)

    changed = services.set_active(Brand.objects.all(), is_active=False, by=editor)

    assert changed == 1
    event = only_event()
    assert (event.action, event.object_id) == ("catalog.brand.retired", hermes.id)
    assert event.changes == {"is_active": {"from": True, "to": False}}


def test_bringing_back_records_restored(editor: User) -> None:
    make_category("Bags", is_active=False)

    services.set_active(Category.objects.all(), is_active=True, by=editor)

    assert actions() == ["catalog.category.restored"]


# ---------- deleting ----------


def test_deleting_an_entry_records_its_last_values(editor: User) -> None:
    typo = make_material("Togoo leather")
    typo_id = typo.id

    services.delete_entry(typo, by=editor)

    assert not Material.objects.exists()
    event = only_event()
    assert (event.action, event.object_id) == ("catalog.material.deleted", typo_id)
    assert event.changes["name"] == {"from": "Togoo leather"}


def test_a_draft_protocol_can_be_deleted_with_a_record(editor: User) -> None:
    draft = make_protocol()

    services.delete_protocol(draft, by=editor)

    assert not CaptureProtocol.objects.exists()
    assert actions() == ["catalog.captureprotocol.deleted"]


def test_an_active_protocol_is_never_deleted(editor: User) -> None:
    active = make_protocol(status="active")

    with pytest.raises(ProtocolNotDraftError):
        services.delete_protocol(active, by=editor)

    assert CaptureProtocol.objects.exists()
    assert not AuditEvent.objects.exists()


# ---------- capture protocols ----------


def test_each_protocol_step_is_recorded(editor: User) -> None:
    bags = make_category("Bags")
    old = make_protocol(category=bags, version=1, status="active")

    draft = services.create_protocol(category=bags, by=editor)
    make_shot(draft)
    services.activate_protocol(draft, by=editor)
    services.retire_protocol(draft, by=editor)
    copy = services.new_draft_from(draft, by=editor)

    assert actions() == [
        "catalog.captureprotocol.created",
        "catalog.captureprotocol.retired",  # the one the new protocol replaced
        "catalog.captureprotocol.activated",
        "catalog.captureprotocol.retired",
        "catalog.captureprotocol.created",
        "catalog.captureprotocol.drafted",
    ]
    replaced = AuditEvent.objects.filter(object_id=old.id).get()
    assert replaced.changes == {"status": {"from": "active", "to": "retired"}}
    drafted = AuditEvent.objects.get(action="catalog.captureprotocol.drafted")
    assert drafted.object_id == copy.id
    assert drafted.changes == {"copied_from": str(draft.id), "shots_copied": 1}


def test_a_refused_activation_records_nothing(editor: User) -> None:
    draft = make_protocol()

    with pytest.raises(Exception, match="shot"):
        services.activate_protocol(draft, by=editor)

    assert not AuditEvent.objects.exists()


# ---------- through the admin site ----------


def test_an_admin_save_records_the_staff_member_ip_and_request(editor_client: Client) -> None:
    response = editor_client.post(
        f"{ADMIN}/brand/add/", {"name": "Hermès", "slug": "hermes", "is_active": "on"}
    )

    assert response.status_code == 302
    event = only_event()
    assert event.actor is not None
    assert event.actor.email == "ed@samwab.com"
    assert event.ip_address == "127.0.0.1"
    assert event.request_id == response[REQUEST_ID_HEADER]


def test_retiring_from_the_list_is_recorded(editor_client: Client) -> None:
    hermes = make_brand()

    editor_client.post(
        f"{ADMIN}/brand/", {"action": "retire_selected", "_selected_action": [str(hermes.id)]}
    )

    assert actions() == ["catalog.brand.retired"]


def test_deleting_from_the_change_page_is_recorded(editor_client: Client) -> None:
    sale = make_sale()

    response = editor_client.post(f"{ADMIN}/comparablesale/{sale.id}/delete/", {"post": "yes"})

    assert response.status_code == 302
    assert not ComparableSale.objects.exists()
    assert actions() == ["catalog.comparablesale.deleted"]


def test_deleting_from_the_list_records_each_row(editor_client: Client) -> None:
    one, two = make_material("Typo one"), make_material("Typo two")

    response: Any = editor_client.post(
        f"{ADMIN}/material/",
        {
            "action": "delete_selected",
            "_selected_action": [str(one.id), str(two.id)],
            "post": "yes",
        },
    )

    assert response.status_code == 302
    assert not Material.objects.exists()
    assert actions() == ["catalog.material.deleted", "catalog.material.deleted"]


def test_shots_added_changed_and_removed_in_the_admin_are_recorded(editor_client: Client) -> None:
    protocol = make_protocol()
    keep = make_shot(protocol, code="heat_stamp", sort_order=1)
    drop = make_shot(protocol, code="zip_pull", sort_order=2)

    def shot(index: int, **values: str) -> dict[str, str]:
        return {f"shots-{index}-{name}": value for name, value in values.items()}

    common = {"kind": "photo", "instrument": "phone", "is_required": "on"}
    response = editor_client.post(
        f"{ADMIN}/captureprotocol/{protocol.id}/change/",
        {
            "shots-TOTAL_FORMS": "3",
            "shots-INITIAL_FORMS": "2",
            **shot(
                0,
                id=str(keep.id),
                code="heat_stamp",
                name="Heat stamp, close",
                sort_order="1",
                **common,
            ),
            **shot(
                1,
                id=str(drop.id),
                code="zip_pull",
                name="Zip pull",
                sort_order="2",
                DELETE="on",
                **common,
            ),
            **shot(2, code="lining", name="Lining", sort_order="3", **common),
        },
    )

    assert response.status_code == 302
    assert sorted(actions()) == [
        "catalog.captureshot.changed",
        "catalog.captureshot.created",
        "catalog.captureshot.deleted",
    ]
    changed = AuditEvent.objects.get(action="catalog.captureshot.changed")
    assert changed.changes == {"name": {"from": "Heat stamp", "to": "Heat stamp, close"}}
    assert AuditEvent.objects.get(action="catalog.captureshot.deleted").object_id == drop.id
