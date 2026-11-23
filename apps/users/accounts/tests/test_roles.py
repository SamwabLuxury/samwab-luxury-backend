"""Tests for the role groups created by migration 0003."""

import pytest
from django.contrib.auth.models import Group

from apps.users.accounts import roles


@pytest.mark.django_db
def test_every_role_has_its_group() -> None:
    names = set(Group.objects.values_list("name", flat=True))

    assert set(roles.ALL_ROLES) <= names


def test_the_role_list_matches_the_contract() -> None:
    assert roles.ALL_ROLES == (
        "owner",
        "dealer",
        "intake_staff",
        "reviewer",
        "catalog_editor",
        "partner",
        "support",
        "finance",
        "admin",
    )


def test_there_is_no_buyer_role() -> None:
    assert "buyer" not in roles.ALL_ROLES


def test_the_migration_creates_the_same_names() -> None:
    from importlib import import_module

    migration = import_module("apps.users.accounts.migrations.0003_role_groups")

    assert migration.ROLE_NAMES == roles.ALL_ROLES
