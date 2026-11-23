"""Tests for the catalog reads the public API uses."""

import pytest

from apps.inventory.catalog import selectors
from apps.inventory.catalog.tests.helpers import make_brand, make_category, make_product_model

pytestmark = pytest.mark.django_db


def slugs(rows: object) -> list[str]:
    return [row.slug for row in rows]  # type: ignore[attr-defined]


def test_public_brands_leave_out_retired_ones() -> None:
    make_brand("Hermès")
    make_brand("Old House", is_active=False)

    assert slugs(selectors.public_brands()) == ["hermes"]


def test_public_categories_leave_out_retired_ones() -> None:
    make_category("Bags")
    make_category("Watches", is_active=False)

    assert slugs(selectors.public_categories()) == ["bags"]


def test_no_rows_means_an_empty_list() -> None:
    assert list(selectors.public_brands()) == []
    assert list(selectors.public_categories()) == []
    assert list(selectors.public_product_models()) == []


class TestPublicProductModels:
    @pytest.fixture(autouse=True)
    def catalog(self) -> None:
        hermes, chanel = make_brand("Hermès"), make_brand("Chanel")
        bags, jewellery = make_category("Bags"), make_category("Jewellery")
        make_product_model("Kelly 28", brand=hermes, category=bags)
        make_product_model("Clic H", brand=hermes, category=jewellery)
        make_product_model("Classic Flap", brand=chanel, category=bags)
        make_product_model("Retired design", brand=chanel, category=bags, is_active=False)

    def test_all_active_designs(self) -> None:
        assert sorted(slugs(selectors.public_product_models())) == [
            "classic-flap",
            "clic-h",
            "kelly-28",
        ]

    def test_filter_by_brand_slug(self) -> None:
        found = selectors.public_product_models(brand_slug="hermes")

        assert sorted(slugs(found)) == ["clic-h", "kelly-28"]

    def test_filter_by_category_slug(self) -> None:
        found = selectors.public_product_models(category_slug="bags")

        assert sorted(slugs(found)) == ["classic-flap", "kelly-28"]

    def test_filter_by_both(self) -> None:
        found = selectors.public_product_models(brand_slug="hermes", category_slug="bags")

        assert slugs(found) == ["kelly-28"]

    def test_an_unknown_slug_finds_nothing(self) -> None:
        assert list(selectors.public_product_models(brand_slug="no-such-brand")) == []
        assert list(selectors.public_product_models(category_slug="no-such-category")) == []

    def test_designs_of_a_retired_brand_are_hidden(self) -> None:
        make_product_model(
            "Lady",
            brand=make_brand("Retired House", is_active=False),
            category=make_category("Small leather goods"),
        )

        assert "lady" not in slugs(selectors.public_product_models())
        assert list(selectors.public_product_models(brand_slug="retired-house")) == []

    def test_designs_in_a_retired_category_are_hidden(self) -> None:
        make_product_model(
            "Daytona",
            brand=make_brand("Rolex"),
            category=make_category("Watches", is_active=False),
        )

        assert "daytona" not in slugs(selectors.public_product_models())
