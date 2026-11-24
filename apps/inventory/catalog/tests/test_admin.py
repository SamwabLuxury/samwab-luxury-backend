"""Tests for the catalog manager: the admin screens where staff run the catalog."""

from typing import Any

import pytest
from django.db import models
from django.test import Client

from apps.inventory.catalog.models import Brand, Category, Material, ProductModel
from apps.inventory.catalog.tests.helpers import (
    make_brand,
    make_category,
    make_material,
    make_product_model,
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


@pytest.mark.parametrize("screen", ["brand", "category", "productmodel", "material"])
def test_every_list_and_add_screen_opens(boss_client: Client, screen: str) -> None:
    page(boss_client.get(f"{ADMIN}/{screen}/"))
    page(boss_client.get(f"{ADMIN}/{screen}/add/"))


def test_lists_show_and_search_the_rows(boss_client: Client) -> None:
    make_product_model("Kelly 28")
    make_material("Togo leather")

    assert "Kelly 28" in page(boss_client.get(f"{ADMIN}/productmodel/", {"q": "kelly"}))
    assert "Hermès" in page(boss_client.get(f"{ADMIN}/brand/", {"q": "herm"}))
    assert "Bags" in page(boss_client.get(f"{ADMIN}/category/", {"q": "bag"}))
    assert "Togo leather" in page(boss_client.get(f"{ADMIN}/material/", {"q": "togo"}))


def test_change_screens_open(boss_client: Client) -> None:
    kelly = make_product_model("Kelly 28")
    togo = make_material("Togo leather")

    page(boss_client.get(f"{ADMIN}/brand/{kelly.brand_id}/change/"))
    page(boss_client.get(f"{ADMIN}/category/{kelly.category_id}/change/"))
    page(boss_client.get(f"{ADMIN}/productmodel/{kelly.id}/change/"))
    page(boss_client.get(f"{ADMIN}/material/{togo.id}/change/"))


def test_staff_can_add_a_brand(boss_client: Client) -> None:
    response = boss_client.post(
        f"{ADMIN}/brand/add/", {"name": "Hermès", "slug": "hermes", "is_active": "on"}
    )

    assert response.status_code == 302
    assert Brand.objects.get().slug == "hermes"


def test_a_slug_cannot_change_after_it_is_created(boss_client: Client) -> None:
    """Slugs are in the web app's links. Renaming keeps the slug, so old links still work."""
    hermes = make_brand("Hermès")

    response = boss_client.post(
        f"{ADMIN}/brand/{hermes.id}/change/",
        {"name": "Hermès Paris", "slug": "hermes-paris", "is_active": "on"},
    )

    assert response.status_code == 302
    hermes.refresh_from_db()
    assert (hermes.name, hermes.slug) == ("Hermès Paris", "hermes")


def test_saving_a_category_in_the_admin_records_who_changed_it(
    boss_client: Client, boss: User
) -> None:
    response = boss_client.post(
        f"{ADMIN}/category/add/",
        {
            "name": "Bags",
            "slug": "bags",
            "attribute_schema": "{}",
            "flaw_types": '["pilling"]',
            "default_storage": "shelf",
            "default_hs_code": "420221",
            "sort_order": "1",
            "is_active": "on",
        },
    )

    assert response.status_code == 302
    bags = Category.objects.get()
    assert bags.updated_by == boss
    assert bags.flaw_types == ["pilling"]


def test_the_admin_refuses_a_category_loop(boss_client: Client) -> None:
    bags = make_category("Bags")
    child = make_category("Top-handle bags", parent=bags)

    response = boss_client.post(
        f"{ADMIN}/category/{bags.id}/change/",
        {
            "name": "Bags",
            "parent": str(child.id),
            "attribute_schema": "{}",
            "flaw_types": "[]",
            "default_storage": "shelf",
            "default_hs_code": "",
            "sort_order": "0",
            "is_active": "on",
        },
    )

    assert "cannot sit under itself" in page(response)
    bags.refresh_from_db()
    assert bags.parent is None


@pytest.mark.parametrize("model", [Brand, Category, ProductModel])
def test_brands_categories_and_designs_are_retired_not_deleted(
    boss_client: Client, model: type[models.Model]
) -> None:
    kelly = make_product_model()
    rows: dict[type[models.Model], models.Model] = {
        Brand: kelly.brand,
        Category: kelly.category,
        ProductModel: kelly,
    }
    row = rows[model]
    screen = model._meta.model_name

    response = boss_client.get(f"{ADMIN}/{screen}/{row.pk}/delete/")

    assert response.status_code == 403
    assert model._default_manager.filter(pk=row.pk).exists()


def test_a_material_added_by_mistake_can_be_deleted(boss_client: Client) -> None:
    typo = make_material("Toog leather")

    response = boss_client.post(f"{ADMIN}/material/{typo.id}/delete/", {"post": "yes"})

    assert response.status_code == 302
    assert not Material.objects.exists()


@pytest.mark.parametrize(
    ("action", "active_after"), [("retire_selected", False), ("restore_selected", True)]
)
def test_retire_and_bring_back_from_the_list(
    boss_client: Client, boss: User, action: str, active_after: bool
) -> None:
    bags = make_category("Bags", is_active=not active_after)

    response = boss_client.post(
        f"{ADMIN}/category/", {"action": action, "_selected_action": [str(bags.id)]}
    )

    assert response.status_code == 302
    bags.refresh_from_db()
    assert bags.is_active is active_after
    assert bags.updated_by == boss


def test_staff_can_reorder_categories_from_the_list(boss_client: Client) -> None:
    bags = make_category("Bags")

    response = boss_client.post(
        f"{ADMIN}/category/",
        {
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "1",
            "form-0-id": str(bags.id),
            "form-0-sort_order": "5",
            "form-0-is_active": "on",
            "_save": "Save",
        },
    )

    assert response.status_code == 302
    bags.refresh_from_db()
    assert bags.sort_order == 5
