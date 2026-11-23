"""Tests for the public catalog endpoints the store's menus and filters use."""

from typing import Any

import pytest
from django.test import Client

from apps.inventory.catalog.tests.helpers import make_brand, make_category, make_product_model
from apps.users.accounts.models import User

pytestmark = pytest.mark.django_db

BRANDS = "/api/v1/brands/"
CATEGORIES = "/api/v1/categories/"
PRODUCT_MODELS = "/api/v1/product-models/"


def results(response: Any) -> list[dict[str, Any]]:
    assert response.status_code == 200, response.content
    body = response.json()
    assert set(body) == {"next", "previous", "results"}
    return list(body["results"])


def every_page(client: Client, url: str, **params: Any) -> list[str]:
    """Follow ``next`` from the first page to the last; return every slug seen."""
    page = client.get(url, params).json()
    seen = [row["slug"] for row in page["results"]]
    while page["next"] is not None:
        page = client.get(url, {**params, "cursor": page["next"]}).json()
        seen += [row["slug"] for row in page["results"]]
    return seen


# ---------- brands ----------


def test_brands_are_public_and_match_the_contract(client: Client) -> None:
    hermes = make_brand("Hermès")

    rows = results(client.get(BRANDS))

    assert rows == [{"id": str(hermes.id), "name": "Hermès", "slug": "hermes"}]


def test_brands_are_in_alphabetical_order_and_leave_out_retired_ones(client: Client) -> None:
    for name in ("Hermès", "Chanel", "Rolex"):
        make_brand(name)
    make_brand("Ancienne Maison", is_active=False)

    rows = results(client.get(BRANDS))

    assert [row["slug"] for row in rows] == ["chanel", "hermes", "rolex"]


def test_no_brands_is_an_empty_page(client: Client) -> None:
    response = client.get(BRANDS)

    assert response.json() == {"next": None, "previous": None, "results": []}


def test_brands_page_through_every_row_once(client: Client) -> None:
    for number in range(30):
        make_brand(f"Brand {number:02d}")

    seen = every_page(client, BRANDS)

    assert seen == [f"brand-{number:02d}" for number in range(30)]


def test_a_logged_in_user_sees_the_same_brands(client: Client) -> None:
    make_brand("Hermès")
    client.force_login(User.objects.create_user("ada@example.com", "correct-horse-9"))

    assert [row["slug"] for row in results(client.get(BRANDS))] == ["hermes"]


@pytest.mark.parametrize("url", [BRANDS, CATEGORIES, PRODUCT_MODELS])
@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_the_catalog_is_read_only(client: Client, url: str, method: str) -> None:
    """Staff change the catalog in the admin site, never through the public API."""
    response = getattr(client, method)(url, {}, content_type="application/json")

    assert response.status_code == 405
    assert response.json()["code"] == "method_not_allowed"


@pytest.mark.parametrize("url", [BRANDS, CATEGORIES, PRODUCT_MODELS])
def test_each_list_is_one_database_query(
    client: Client, url: str, django_assert_num_queries: Any
) -> None:
    for number in range(5):
        make_product_model(
            f"Design {number}",
            brand=make_brand(f"Brand {number}"),
            category=make_category(f"Category {number}"),
        )

    with django_assert_num_queries(1):
        assert len(results(client.get(url))) == 5


@pytest.mark.parametrize("url", [BRANDS, CATEGORIES, PRODUCT_MODELS])
def test_a_broken_cursor_is_a_clear_error(client: Client, url: str) -> None:
    response = client.get(url, {"cursor": "not-a-real-cursor"})

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


# ---------- categories ----------


def test_categories_match_the_contract(client: Client) -> None:
    bags = make_category("Bags", attribute_schema={"type": "object"})
    top_handle = make_category("Top-handle bags", parent=bags)

    rows = results(client.get(CATEGORIES))

    assert rows == [
        {
            "id": str(bags.id),
            "parent_id": None,
            "name": "Bags",
            "slug": "bags",
            "attribute_schema": {"type": "object"},
        },
        {
            "id": str(top_handle.id),
            "parent_id": str(bags.id),
            "name": "Top-handle bags",
            "slug": "top-handle-bags",
            "attribute_schema": {},
        },
    ]


def test_categories_follow_the_menu_order_staff_set(client: Client) -> None:
    make_category("Watches", sort_order=2)
    make_category("Bags", sort_order=1)
    make_category("Jewellery", sort_order=2)
    make_category("Retired", sort_order=0, is_active=False)

    rows = results(client.get(CATEGORIES))

    # Lowest sort_order first; the same sort_order goes alphabetically.
    assert [row["slug"] for row in rows] == ["bags", "jewellery", "watches"]


def test_categories_with_the_same_sort_order_page_through_every_row_once(
    client: Client,
) -> None:
    """The cursor stands on sort_order. Many rows share 0, so paging must still be exact."""
    for number in range(60):
        make_category(f"Category {number:02d}")

    seen = every_page(client, CATEGORIES)

    assert seen == [f"category-{number:02d}" for number in range(60)]


def test_previous_goes_back_through_tied_categories(client: Client) -> None:
    for number in range(30):
        make_category(f"Category {number:02d}")
    first = client.get(CATEGORIES).json()
    second = client.get(CATEGORIES, {"cursor": first["next"]}).json()

    back = client.get(CATEGORIES, {"cursor": second["previous"]}).json()

    assert back["results"] == first["results"]


# ---------- product models (named designs) ----------


@pytest.fixture
def catalog() -> dict[str, Any]:
    hermes, chanel = make_brand("Hermès"), make_brand("Chanel")
    bags, jewellery = make_category("Bags"), make_category("Jewellery")
    return {
        "kelly": make_product_model(
            "Kelly 28", brand=hermes, category=bags, era_from=1956, department="women"
        ),
        "clic": make_product_model("Clic H", brand=hermes, category=jewellery),
        "flap": make_product_model("Classic Flap", brand=chanel, category=bags),
        "retired": make_product_model("Retired", brand=chanel, category=bags, is_active=False),
    }


def test_product_models_match_the_contract(client: Client, catalog: dict[str, Any]) -> None:
    kelly = catalog["kelly"]

    rows = results(client.get(PRODUCT_MODELS, {"brand": "hermes", "category": "bags"}))

    assert rows == [
        {
            "id": str(kelly.id),
            "brand_id": str(kelly.brand_id),
            "category_id": str(kelly.category_id),
            "name": "Kelly 28",
            "slug": "kelly-28",
            "era_from": 1956,
            "era_to": None,
        }
    ]


def test_product_models_without_filters(client: Client, catalog: dict[str, Any]) -> None:
    rows = results(client.get(PRODUCT_MODELS))

    assert [row["slug"] for row in rows] == ["classic-flap", "clic-h", "kelly-28"]


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"brand": "hermes"}, ["clic-h", "kelly-28"]),
        ({"category": "bags"}, ["classic-flap", "kelly-28"]),
        ({"brand": "chanel", "category": "jewellery"}, []),
        ({"brand": "no-such-brand"}, []),
        ({"brand": ""}, ["classic-flap", "clic-h", "kelly-28"]),
        ({"brand": "hermes", "unknown": "ignored"}, ["clic-h", "kelly-28"]),
    ],
)
def test_product_model_filters(
    client: Client, catalog: dict[str, Any], params: dict[str, str], expected: list[str]
) -> None:
    rows = results(client.get(PRODUCT_MODELS, params))

    assert [row["slug"] for row in rows] == expected


@pytest.mark.parametrize(
    ("params", "field"),
    [
        ({"brand": "Hermès!"}, "brand"),
        ({"category": "two words"}, "category"),
        ({"brand": "x" * 161}, "brand"),
    ],
)
def test_a_badly_formed_filter_is_a_validation_error(
    client: Client, params: dict[str, str], field: str
) -> None:
    response = client.get(PRODUCT_MODELS, params)

    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "validation_error"
    assert [error["field"] for error in body["errors"]] == [field]


def test_the_filter_is_kept_while_paging(client: Client) -> None:
    hermes, chanel, bags = make_brand("Hermès"), make_brand("Chanel"), make_category("Bags")
    for number in range(30):
        make_product_model(f"Hermes {number:02d}", brand=hermes, category=bags)
        make_product_model(f"Chanel {number:02d}", brand=chanel, category=bags)

    seen = every_page(client, PRODUCT_MODELS, brand="hermes")

    assert seen == [f"hermes-{number:02d}" for number in range(30)]


def test_designs_with_the_same_slug_page_both_ways(client: Client) -> None:
    """Several brands can have a design called "classic"; paging must still be exact."""
    bags = make_category("Bags")
    for number in range(30):
        make_product_model("Classic", brand=make_brand(f"Brand {number:02d}"), category=bags)
    first = client.get(PRODUCT_MODELS).json()
    second = client.get(PRODUCT_MODELS, {"cursor": first["next"]}).json()

    back = client.get(PRODUCT_MODELS, {"cursor": second["previous"]}).json()

    assert len(first["results"]) + len(second["results"]) == 30
    assert {row["id"] for row in first["results"]}.isdisjoint(
        row["id"] for row in second["results"]
    )
    assert back["results"] == first["results"]


# ---------- the API description ----------


def test_the_api_description_matches_the_contract(client: Client) -> None:
    paths = client.get("/api/v1/schema/", {"format": "json"}).json()["paths"]

    for url, operation_id in [
        (BRANDS, "brands_list"),
        (CATEGORIES, "categories_list"),
        (PRODUCT_MODELS, "product_models_list"),
    ]:
        operation = paths[url]["get"]
        assert operation["operationId"] == operation_id
        assert operation["tags"] == ["Catalog"]
        # No login: the operation lists no security scheme, as in the contract.
        assert operation.get("security", []) in ([], [{}])
        assert "cursor" in [parameter["name"] for parameter in operation["parameters"]]

    filters = {p["name"] for p in paths[PRODUCT_MODELS]["get"]["parameters"]}
    assert {"brand", "category", "cursor"} <= filters
