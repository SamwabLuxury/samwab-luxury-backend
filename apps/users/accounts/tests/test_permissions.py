"""Tests for the permissions each staff role holds, set from code after every migrate."""

from typing import Any

import pytest
from django.apps import apps as global_apps
from django.contrib.auth.models import Group, Permission
from django.test import Client

from apps.inventory.catalog.permissions import ROLE_PERMISSIONS as CATALOG
from apps.inventory.catalog.tests.helpers import make_brand, make_product_model
from apps.inventory.pieces.permissions import ROLE_PERMISSIONS as PIECES
from apps.inventory.pieces.tests.helpers import make_piece
from apps.users.accounts import roles
from apps.users.accounts.models import User
from apps.users.accounts.permissions import sync_role_permissions
from apps.users.accounts.tests.helpers import admin_login, make_staff

pytestmark = pytest.mark.django_db

CATALOG_EDITING = (
    {
        f"{action}_{model}"
        for model in ("brand", "category", "productmodel", "captureprotocol", "comparablesale")
        for action in ("add", "change", "view")
    }
    | {
        f"{action}_{model}"
        for model in ("material", "captureshot")
        for action in ("add", "change", "delete", "view")
    }
    | {"delete_captureprotocol", "delete_comparablesale"}
)


def codes(role: str, app_label: str | None = None) -> set[str]:
    found = Group.objects.get(name=role).permissions.all()
    if app_label:
        found = found.filter(content_type__app_label=app_label)
    return set(found.values_list("codename", flat=True))


def staff_in(role: str) -> User:
    user: User = make_staff(f"{role}@samwab.com", role)
    return user


def status(client: Client, url: str) -> int:
    response: Any = client.get(url)
    return int(response.status_code)


# ---------- what each role holds ----------


def test_a_catalog_editor_runs_the_whole_catalog() -> None:
    assert codes(roles.CATALOG_EDITOR, "catalog") == CATALOG_EDITING


def test_intake_staff_register_pieces_and_read_the_catalog() -> None:
    assert codes(roles.INTAKE_STAFF, "pieces") == {
        "add_piece",
        "change_piece",
        "view_piece",
        "add_piecematerial",
        "change_piecematerial",
        "delete_piecematerial",
        "view_piecematerial",
        "add_media",
        "change_media",
        "delete_media",
        "view_media",
    }
    assert codes(roles.INTAKE_STAFF, "catalog") == {
        "view_brand",
        "view_category",
        "view_productmodel",
        "view_material",
    }


def test_no_role_may_delete_a_piece_or_a_retire_only_catalog_row() -> None:
    for role in roles.ALL_ROLES:
        held = codes(role)
        assert not held & {"delete_piece", "delete_brand", "delete_category", "delete_productmodel"}


STAFF_ROLES = {roles.CATALOG_EDITOR, roles.INTAKE_STAFF, roles.SUPPORT, roles.FINANCE}


def test_roles_without_screens_yet_hold_nothing() -> None:
    for role in set(roles.ALL_ROLES) - STAFF_ROLES:
        assert codes(role) == set(), role


def expected(role: str, grants: list[tuple[str, Any]]) -> set[str]:
    return {
        f"{action}_{model}"
        for _, table in grants
        for model, actions in table.get(role, {}).items()
        for action in actions
    }


def test_each_staff_role_holds_exactly_what_the_grant_files_say() -> None:
    """E16: listings, drops, orders, payments and the mailing list joined the grants."""
    modules = [
        getattr(config.module, "permissions", None)
        for config in global_apps.get_app_configs()
        if config.name.startswith("apps.")
    ]
    grants = [
        (module.__name__, module.ROLE_PERMISSIONS)
        for module in modules
        if module is not None and hasattr(module, "ROLE_PERMISSIONS")
    ]
    for role in STAFF_ROLES:
        assert codes(role) == expected(role, grants), role


def test_support_and_finance_only_look() -> None:
    for role in (roles.SUPPORT, roles.FINANCE):
        assert {code.split("_", 1)[0] for code in codes(role)} == {"view"}, role


def test_nobody_but_a_superuser_reads_the_audit_log_yet() -> None:
    for role in roles.ALL_ROLES:
        assert "view_auditevent" not in codes(role)


def test_every_role_named_in_the_grants_exists() -> None:
    assert set(CATALOG) | set(PIECES) <= set(roles.ALL_ROLES)


# ---------- the sync ----------


def test_the_sync_puts_back_what_code_says_for_that_app() -> None:
    editor = Group.objects.get(name=roles.CATALOG_EDITOR)
    editor.permissions.add(Permission.objects.get(codename="delete_brand"))
    editor.permissions.remove(Permission.objects.get(codename="add_brand"))
    piece_view = Permission.objects.get(codename="view_piece")
    editor.permissions.add(piece_view)

    sync_role_permissions(global_apps.get_app_config("catalog"), CATALOG)

    assert codes(roles.CATALOG_EDITOR, "catalog") == CATALOG_EDITING
    assert piece_view in editor.permissions.all()  # another app's grants are left alone


def test_running_the_sync_twice_changes_nothing() -> None:
    before = codes(roles.INTAKE_STAFF)

    sync_role_permissions(global_apps.get_app_config("pieces"), PIECES)
    sync_role_permissions(global_apps.get_app_config("pieces"), PIECES)

    assert codes(roles.INTAKE_STAFF) == before


def test_the_sync_refuses_an_unknown_role() -> None:
    with pytest.raises(ValueError, match="buyer"):
        sync_role_permissions(
            global_apps.get_app_config("catalog"), {"buyer": {"brand": ("view",)}}
        )


def test_the_sync_refuses_a_permission_that_does_not_exist() -> None:
    with pytest.raises(ValueError, match=r"catalog\.fly_brand"):
        sync_role_permissions(
            global_apps.get_app_config("catalog"), {roles.CATALOG_EDITOR: {"brand": ("fly",)}}
        )


# ---------- what the roles see in the admin site ----------


def test_a_catalog_editor_uses_the_catalog_screens_but_not_pieces(client: Client) -> None:
    admin_login(client, staff_in(roles.CATALOG_EDITOR))
    brand = make_brand()

    assert status(client, "/admin/catalog/brand/") == 200
    assert status(client, "/admin/catalog/brand/add/") == 200
    assert status(client, f"/admin/catalog/brand/{brand.id}/change/") == 200
    assert status(client, "/admin/catalog/captureprotocol/add/") == 200
    assert status(client, "/admin/pieces/piece/") == 403
    assert status(client, "/admin/accounts/user/") == 403


def test_intake_staff_register_pieces_but_cannot_edit_the_catalog(client: Client) -> None:
    admin_login(client, staff_in(roles.INTAKE_STAFF))
    piece = make_piece(product_model=make_product_model())

    assert status(client, "/admin/pieces/piece/add/") == 200
    assert status(client, f"/admin/pieces/piece/{piece.id}/change/") == 200
    assert status(client, "/admin/catalog/brand/") == 200  # read only
    assert status(client, "/admin/catalog/brand/add/") == 403
    html = client.get(f"/admin/catalog/brand/{piece.brand_id}/change/").content.decode()
    assert 'name="_save"' not in html
    assert status(client, "/admin/catalog/comparablesale/") == 403


def test_intake_staff_can_search_the_catalog_while_registering(client: Client) -> None:
    admin_login(client, staff_in(roles.INTAKE_STAFF))
    make_brand("Hermès")

    response = client.get(
        "/admin/autocomplete/",
        {"app_label": "pieces", "model_name": "piece", "field_name": "brand", "term": "herm"},
    )

    assert response.status_code == 200
    assert [row["text"] for row in response.json()["results"]] == ["Hermès"]


def test_a_role_alone_does_not_open_the_admin_site(client: Client) -> None:
    clerk = staff_in(roles.CATALOG_EDITOR)
    clerk.is_staff = False
    clerk.save()
    admin_login(client, clerk)

    assert status(client, "/admin/catalog/brand/") == 302  # to the admin login page
