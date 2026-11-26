"""Shop totals and filter counts (build E18).

The Figma shop shows "1,284 pieces", "Show 4 more · 1,280 left", a "Find a house"
list with a count per brand, and no-results suggestions such as "See Hermès at any
price · 214 pieces". So:

- ``GET /api/v1/listings/`` adds ``count``: every piece matching the filters, on
  every page (``results`` is one page of them).
- ``GET /api/v1/listings/facets/`` takes the same filters and answers ``total``,
  ``brands`` and ``categories``, each ``{slug, name, count}``. A brand's count leaves
  out the brand filter (and a category's the category filter), so the list of
  houses keeps every house while one is chosen.

Both follow the shop's own rules: lots of a drop that has not closed are not counted.
"""

from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.inventory.catalog.models import Brand, Category
from apps.inventory.catalog.tests.helpers import make_brand, make_category
from apps.shop.listings.models import DropLot
from apps.shop.listings.tests.helpers import make_live_listing, ready_piece
from apps.shop.listings.tests.test_drops import make_drop

pytestmark = pytest.mark.django_db

LIST = "/api/v1/listings/"
FACETS = "/api/v1/listings/facets/"


def brand(name: str) -> Brand:
    return Brand.objects.filter(name=name).first() or make_brand(name)


def category(name: str, parent: Category | None = None) -> Category:
    return Category.objects.filter(name=name).first() or make_category(name, parent=parent)


def stock(brand_name: str, category_name: str, *, ask: int = 1_000_000, **piece: Any) -> None:
    make_live_listing(
        ready_piece(brand=brand(brand_name), category=category(category_name), **piece),
        ask_minor=ask,
    )


@pytest.fixture
def shop() -> None:
    """Three Hermès bags, one Chanel bag, one Cartier bracelet (under Jewellery)."""
    jewellery = category("Jewellery")
    category("Bracelets", parent=jewellery)
    stock("Hermès", "Bags", ask=1_450_000)
    stock("Hermès", "Bags", ask=900_000)
    stock("Hermès", "Bags", ask=80_000)
    stock("Chanel", "Bags", ask=620_000)
    stock("Cartier", "Bracelets", ask=95_000)


def get(path: str, **params: Any) -> dict[str, Any]:
    response = APIClient().get(path, params)
    assert response.status_code == 200, response.content
    return response.json()  # type: ignore[no-any-return]


# ---------- count on the shop list ----------


def test_the_shop_list_says_how_many_pieces_match(shop: None) -> None:
    body = get(LIST, page_size=2)

    assert body["count"] == 5
    assert len(body["results"]) == 2  # one page; "Show 2 more · 3 left" is count minus shown


def test_the_count_follows_the_filters(shop: None) -> None:
    assert get(LIST, brand="hermes")["count"] == 3
    assert get(LIST, price_max=100_000)["count"] == 2  # "everything under $1,000"
    assert get(LIST, category="jewellery")["count"] == 1  # includes Bracelets
    assert get(LIST, brand="nobody")["count"] == 0


def test_every_page_carries_the_same_count(shop: None) -> None:
    first = get(LIST, page_size=2)
    second = get(LIST, page_size=2, cursor=first["next"])

    assert second["count"] == first["count"] == 5


def test_lots_of_a_running_drop_are_not_counted(shop: None) -> None:
    drop = make_drop("members", number=9, name="Evening Edit")
    DropLot.objects.create(drop=drop, listing=make_live_listing(ready_piece()), lot_number=1)

    assert get(LIST)["count"] == 5
    assert get(FACETS)["total"] == 5


def test_lots_of_a_closed_drop_are_counted(shop: None) -> None:
    drop = make_drop("closed", number=8, name="Everyday Classics")
    DropLot.objects.create(drop=drop, listing=make_live_listing(ready_piece()), lot_number=1)

    assert get(LIST)["count"] == 6


# ---------- facets ----------


def test_facets_give_the_total_and_a_count_per_house_and_category(shop: None) -> None:
    body = get(FACETS)

    assert body["total"] == 5
    assert body["brands"] == [  # by name, as a list of houses reads
        {"slug": "cartier", "name": "Cartier", "count": 1},
        {"slug": "chanel", "name": "Chanel", "count": 1},
        {"slug": "hermes", "name": "Hermès", "count": 3},
    ]
    # A category under another is counted in its top category, as the shop filter works.
    assert body["categories"] == [
        {"slug": "bags", "name": "Bags", "count": 4},
        {"slug": "jewellery", "name": "Jewellery", "count": 1},
    ]


def test_choosing_a_house_keeps_every_house_in_the_house_list(shop: None) -> None:
    body = get(FACETS, brand="hermes", category="bags")

    assert body["total"] == 3
    # Brand counts ignore the brand filter but keep the others (here: bags).
    assert [(b["slug"], b["count"]) for b in body["brands"]] == [("chanel", 1), ("hermes", 3)]
    # Category counts ignore the category filter but keep the brand.
    assert [(c["slug"], c["count"]) for c in body["categories"]] == [("bags", 3)]


def test_facets_take_every_shop_filter(shop: None) -> None:
    body = get(FACETS, price_max=100_000)

    assert body["total"] == 2
    assert {b["slug"]: b["count"] for b in body["brands"]} == {"cartier": 1, "hermes": 1}


def test_no_results_still_suggests_the_house_at_any_price(shop: None) -> None:
    """Figma: "See Hermès at any price · 214 pieces" when the price filter finds nothing."""
    narrow = get(FACETS, brand="hermes", price_max=1_000)
    any_price = get(FACETS, brand="hermes")

    assert narrow["total"] == 0
    assert any_price["total"] == 3


def test_houses_with_no_piece_for_sale_are_left_out(shop: None) -> None:
    make_brand("Goyard")

    assert "goyard" not in [b["slug"] for b in get(FACETS)["brands"]]


def test_bad_filters_are_refused_like_the_shop_list(shop: None) -> None:
    response = APIClient().get(FACETS, {"price_max": "cheap"})

    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"


def test_facets_need_no_login_and_change_nothing(shop: None) -> None:
    assert APIClient().get(FACETS).status_code == 200
    assert APIClient().post(FACETS, {}).status_code == 405


def test_facets_run_a_fixed_number_of_queries(
    shop: None, django_assert_max_num_queries: Any
) -> None:
    stock("Goyard", "Bags")
    stock("Dior", "Jewellery")

    # Total, houses, categories and the category names: four, whatever the stock.
    with django_assert_max_num_queries(4):
        get(FACETS, q="bag")
