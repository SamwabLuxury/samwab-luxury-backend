"""Tests for the catalog writes staff make in the catalog manager."""

import pytest
from django.core.exceptions import ValidationError

from apps.accounts.models import User
from apps.catalog import services
from apps.catalog.models import Brand, Category, ProductModel
from apps.catalog.tests.helpers import make_brand, make_category, make_product_model

pytestmark = pytest.mark.django_db


@pytest.fixture
def editor() -> User:
    return User.objects.create_user("editor@samwab.com", "correct-horse-9")


def test_saving_a_category_records_who_changed_it(editor: User) -> None:
    bags = Category(name="Bags", slug="bags")

    services.save_entry(bags, by=editor)

    bags.refresh_from_db()
    assert bags.updated_by == editor


def test_saving_a_brand_works_without_an_updated_by_column(editor: User) -> None:
    brand = Brand(name="Hermès", slug="hermes")

    services.save_entry(brand, by=editor)

    assert Brand.objects.get().name == "Hermès"


def test_saving_checks_the_rules_first(editor: User) -> None:
    bags = make_category("Bags")
    child = make_category("Top-handle bags", parent=bags)
    bags.parent = child

    with pytest.raises(ValidationError):
        services.save_entry(bags, by=editor)

    bags.refresh_from_db()
    assert bags.parent is None


def test_retire_and_bring_back_brands(editor: User) -> None:
    hermes, chanel = make_brand("Hermès"), make_brand("Chanel")
    before = hermes.updated_at

    changed = services.set_active(Brand.objects.filter(pk=hermes.pk), is_active=False, by=editor)

    hermes.refresh_from_db()
    chanel.refresh_from_db()
    assert changed == 1
    assert hermes.is_active is False
    assert hermes.updated_at > before
    assert chanel.is_active is True

    services.set_active(Brand.objects.all(), is_active=True, by=editor)
    hermes.refresh_from_db()
    assert hermes.is_active is True


def test_retiring_a_category_records_who_did_it(editor: User) -> None:
    bags = make_category("Bags")

    services.set_active(Category.objects.all(), is_active=False, by=editor)

    bags.refresh_from_db()
    assert bags.is_active is False
    assert bags.updated_by == editor


def test_retiring_keeps_the_designs_and_their_history(editor: User) -> None:
    kelly = make_product_model()

    services.set_active(Brand.objects.all(), is_active=False, by=editor)

    assert ProductModel.objects.get(pk=kelly.pk).brand.is_active is False


def test_retiring_nothing_changes_nothing(editor: User) -> None:
    assert services.set_active(Brand.objects.none(), is_active=False, by=editor) == 0
