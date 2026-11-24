"""E7: what the piece page needs from GET /api/v1/listings/ and /{id}/.

Photo sizes for the grid, the page and the zoom viewer; each photo's optional name
and note; and the lot record, ready to show as rows.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from django.db import connection
from django.test import Client, override_settings
from django.test.utils import CaptureQueriesContext

from apps.inventory.catalog.models import Category
from apps.inventory.catalog.tests.helpers import make_brand, make_category, make_product_model
from apps.inventory.pieces.models import Media
from apps.shop.listings.tests.helpers import give_photo, make_live_listing, ready_piece

pytestmark = pytest.mark.django_db

LISTINGS = "/api/v1/listings/"
SIZES = {"thumb": 400, "medium": 1200, "zoom": 2400}


def one(client: Client, listing_id: Any) -> dict[str, Any]:
    response = client.get(f"{LISTINGS}{listing_id}/")
    assert response.status_code == 200, response.content
    body: dict[str, Any] = response.json()
    return body


# ---------- photo sizes ----------


def test_each_photo_has_a_link_per_size(client: Client) -> None:
    listing = make_live_listing()

    [photo] = one(client, listing.pk)["piece"]["media"]

    assert set(photo["sizes"]) == {"thumb", "medium", "zoom"}
    # Without Cloudinary (laptops, tests) every size is the photo itself.
    assert photo["sizes"] == dict.fromkeys(("thumb", "medium", "zoom"), photo["url"])
    assert photo["url"].startswith("http://testserver/media/pieces/")


@pytest.fixture
def on_cloudinary() -> Iterator[None]:
    with override_settings(
        CLOUDINARY_URL="cloudinary://123456:not-a-real-secret@samwab-test",
        PHOTO_FOLDER="samwab/live",
        PHOTO_SIZES=SIZES,
        STORAGES={
            "default": {"BACKEND": "apps.platform.core.storage.CloudinaryStorage"},
            "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
        },
    ):
        yield


@pytest.mark.usefixtures("on_cloudinary")
def test_on_cloudinary_each_size_is_a_cloudinary_link(client: Client) -> None:
    listing = make_live_listing()
    stored = Media.objects.get().stored_name.removesuffix(".jpg")

    [photo] = one(client, listing.pk)["piece"]["media"]

    base = "https://res.cloudinary.com/samwab-test/image/upload/"
    assert photo["url"] == f"{base}v1/samwab/live/{stored}.jpg"  # the original, unchanged
    assert photo["sizes"] == {
        "thumb": f"{base}c_limit,h_400,w_400/q_auto/f_auto/v1/samwab/live/{stored}.jpg",
        "medium": f"{base}c_limit,h_1200,w_1200/q_auto/f_auto/v1/samwab/live/{stored}.jpg",
        "zoom": f"{base}c_limit,h_2400,w_2400/q_auto/f_auto/v1/samwab/live/{stored}.jpg",
    }
    assert "not-a-real-secret" not in str(photo)


# ---------- name and note ----------


def test_a_photo_without_a_name_or_note_sends_nulls(client: Client) -> None:
    listing = make_live_listing()

    [photo] = one(client, listing.pk)["piece"]["media"]

    assert photo["label"] is None
    assert photo["caption"] is None


def test_a_photo_with_a_name_and_note_sends_them(client: Client) -> None:
    piece = ready_piece()
    Media.objects.filter(piece=piece).update(label="Stamp", caption="Shallow and clean.")
    listing = make_live_listing(piece)

    [photo] = one(client, listing.pk)["piece"]["media"]

    assert (photo["label"], photo["caption"]) == ("Stamp", "Shallow and clean.")


# ---------- the lot record ----------


@pytest.fixture
def bags() -> Category:
    category: Category = make_category(
        "Bags",
        attribute_schema={
            "type": "object",
            "properties": {
                "leather": {"type": "string", "title": "Leather · colour"},
                "hardware": {"type": "string", "title": "Hardware"},
                "comes_with": {"type": "array", "items": {"type": "string"}, "title": "Comes with"},
                "size_cm": {"type": "object"},
            },
        },
    )
    return category


def test_the_lot_record_lists_the_piece_in_rows(client: Client, bags: Category) -> None:
    design = make_product_model("Kelly 28", brand=make_brand("Hermès"), category=bags)
    piece = ready_piece(
        product_model=design,
        production_year=2019,
        size_label="28",
        condition_grade="very_good",
        attributes={
            "leather": "Togo · Gold",
            "hardware": "Palladium",
            "comes_with": ["Box", "dust bag", "lock", "keys"],
            "size_cm": {"width": 28, "height": 22, "depth": 10},
            "stamp": "D (2019)",
            "boxed": True,
            "note": "",
        },
    )
    listing = make_live_listing(piece)

    record = one(client, listing.pk)["piece"]["lot_record"]

    assert record == [
        {"label": "Maker", "value": "Hermès"},
        {"label": "Model", "value": "Kelly 28"},
        {"label": "Year", "value": "2019"},
        {"label": "Size", "value": "28"},
        {"label": "Grade", "value": "Very good"},
        # Then the attributes, by key, named by the category's schema where it can.
        {"label": "Boxed", "value": "Yes"},
        {"label": "Comes with", "value": "Box, dust bag, lock, keys"},
        {"label": "Hardware", "value": "Palladium"},
        {"label": "Leather · colour", "value": "Togo · Gold"},
        {"label": "Size cm", "value": "depth 10, height 22, width 28"},
        {"label": "Stamp", "value": "D (2019)"},
    ]


def test_the_lot_record_leaves_out_what_the_piece_does_not_have(client: Client) -> None:
    piece = ready_piece(attributes={})
    listing = make_live_listing(piece)

    record = one(client, listing.pk)["piece"]["lot_record"]

    assert record == [{"label": "Maker", "value": piece.brand.name}]


def test_a_design_schema_title_wins_over_the_category(client: Client, bags: Category) -> None:
    design = make_product_model(
        "Kelly 28",
        category=bags,
        attribute_schema={"properties": {"hardware": {"title": "Hardware finish"}}},
    )
    listing = make_live_listing(ready_piece(product_model=design, attributes={"hardware": "Gold"}))

    record = one(client, listing.pk)["piece"]["lot_record"]

    assert {"label": "Hardware finish", "value": "Gold"} in record


def test_the_lot_record_never_shows_private_details(client: Client) -> None:
    piece = ready_piece(
        serial_or_date_code="X-SECRET-42", acquisition_cost_minor=900_000, hs_code="420221"
    )
    listing = make_live_listing(piece)

    body = one(client, listing.pk)

    assert "X-SECRET-42" not in str(body)
    assert "900000" not in str(body)
    assert "420221" not in str(body)


# ---------- speed ----------


def test_more_listings_and_photos_cost_no_more_queries(client: Client) -> None:
    make_live_listing()
    with CaptureQueriesContext(connection) as first:
        assert client.get(LISTINGS).status_code == 200

    for _ in range(3):
        piece = ready_piece()
        give_photo(piece)
        make_live_listing(piece)
    with CaptureQueriesContext(connection) as later:
        assert client.get(LISTINGS).status_code == 200

    assert len(later) == len(first)
