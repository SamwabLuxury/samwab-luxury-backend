"""E8: the piece page's price explainer.

"Recent sales, grade Excellent: $13,100 to $15,400", from the comparable sales staff
enter (same design and grade, last 12 months), plus the staff's own plus and minus
adjustments ("Complete set +$300"). Only on the single-listing answer: shop cards do
not show it, and the list stays one query per page.
"""

from datetime import date, timedelta
from typing import Any

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.test import Client, override_settings
from django.test.utils import CaptureQueriesContext

from apps.inventory.catalog.models import ProductModel
from apps.inventory.catalog.tests.helpers import make_category, make_product_model, make_sale
from apps.platform.audit.models import AuditEvent
from apps.shop.listings import services
from apps.shop.listings.models import Listing, ListingPriceAdjustment
from apps.shop.listings.price_explainer import RecentSales, price_explainer
from apps.shop.listings.tests.helpers import (
    make_admin,
    make_listing,
    make_live_listing,
    ready_piece,
)
from apps.users.accounts.tests.helpers import admin_login

pytestmark = pytest.mark.django_db

TODAY = date(2026, 11, 25)
LISTINGS = "/api/v1/listings/"


@pytest.fixture
def kelly() -> ProductModel:
    design: ProductModel = make_product_model("Kelly 28")
    return design


def listing_for(design: ProductModel, grade: str = "excellent", **fields: Any) -> Listing:
    return make_live_listing(ready_piece(product_model=design, condition_grade=grade, **fields))


def sale(
    design: ProductModel, price: int, days_ago: int, grade: str = "excellent", **kw: Any
) -> Any:
    return make_sale(
        price,
        product_model=design,
        condition_grade=grade,
        sold_on=TODAY - timedelta(days_ago),
        **kw,
    )


def recent_of(listing: Listing) -> RecentSales:
    found = price_explainer(listing, today=TODAY)["recent_sales"]
    assert found is not None
    return found


def money(amount: int) -> dict[str, Any]:
    return {"amount": amount, "currency": "USD"}


# ---------- recent sales ----------


def test_recent_sales_of_the_same_design_and_grade(kelly: ProductModel) -> None:
    listing = listing_for(kelly)
    sale(kelly, 1_310_000, days_ago=100, source="auction")
    sale(kelly, 1_540_000, days_ago=10, source="samwab")
    sale(kelly, 1_450_000, days_ago=50, source="marketplace")

    recent = recent_of(listing)

    assert recent["grade"] == "excellent"
    assert recent["days"] == 365
    assert recent["count"] == 3
    assert recent["low"].amount_minor == 1_310_000
    assert recent["high"].amount_minor == 1_540_000
    assert recent["median"].amount_minor == 1_450_000
    assert [(s["sold_on"], s["price"].amount_minor, s["source"]) for s in recent["sales"]] == [
        (TODAY - timedelta(10), 1_540_000, "samwab"),  # newest first
        (TODAY - timedelta(50), 1_450_000, "marketplace"),
        (TODAY - timedelta(100), 1_310_000, "auction"),
    ]


def test_other_grades_other_designs_and_old_sales_are_left_out(kelly: ProductModel) -> None:
    listing = listing_for(kelly)
    sale(kelly, 1_400_000, days_ago=20)
    sale(kelly, 9_000_000, days_ago=20, grade="new")  # other grade
    sale(kelly, 100_000, days_ago=20, grade="")  # no grade
    sale(make_product_model("Birkin 30", brand=kelly.brand, category=kelly.category), 2_000_000, 20)
    sale(kelly, 500_000, days_ago=366)  # older than a year

    recent = recent_of(listing)

    assert recent["count"] == 1
    assert recent["median"].amount_minor == 1_400_000


def test_a_sale_exactly_a_year_old_still_counts(kelly: ProductModel) -> None:
    listing = listing_for(kelly)
    sale(kelly, 1_200_000, days_ago=365)

    assert recent_of(listing)["count"] == 1


def test_the_median_of_an_even_count_is_halfway_rounded_up_to_the_cent(kelly: ProductModel) -> None:
    listing = listing_for(kelly)
    for price, days in ((1_000_000, 1), (1_000_001, 2), (1_500_000, 3), (2_000_000, 4)):
        sale(kelly, price, days)

    recent = recent_of(listing)

    assert recent["median"].amount_minor == 1_250_001  # (1,000,001 + 1,500,000) / 2 = 1,250,000.5


@override_settings(COMPARABLE_SALES_SHOWN=2, COMPARABLE_SALES_DAYS=30)
def test_how_many_sales_and_how_far_back_are_settings(kelly: ProductModel) -> None:
    listing = listing_for(kelly)
    for price, days in ((1_100_000, 1), (1_200_000, 2), (1_300_000, 3), (1_400_000, 31)):
        sale(kelly, price, days)

    recent = recent_of(listing)

    assert recent["days"] == 30
    assert [s["price"].amount_minor for s in recent["sales"]] == [1_100_000, 1_200_000]
    assert recent["median"].amount_minor == 1_150_000  # the range and median use the sales shown


def test_a_piece_without_a_design_uses_its_brand_and_category(kelly: ProductModel) -> None:
    listing = make_live_listing(
        ready_piece(brand=kelly.brand, category=kelly.category, condition_grade="good")
    )
    sale(kelly, 800_000, days_ago=5, grade="good")  # any design of that brand and category
    make_sale(
        700_000,
        brand=kelly.brand,
        category=make_category("Shoes"),
        condition_grade="good",
        sold_on=TODAY,
    )

    recent = recent_of(listing)

    assert recent["count"] == 1
    assert recent["median"].amount_minor == 800_000


def test_no_grade_or_no_matching_sales_means_no_recent_sales(kelly: ProductModel) -> None:
    ungraded = listing_for(kelly, grade="")
    sale(kelly, 1_400_000, days_ago=5)
    graded_but_alone = listing_for(
        make_product_model("Constance 24", brand=kelly.brand, category=kelly.category)
    )

    assert price_explainer(ungraded, today=TODAY)["recent_sales"] is None
    assert price_explainer(graded_but_alone, today=TODAY)["recent_sales"] is None


# ---------- staff adjustments ----------


def adjust(
    listing: Listing, label: str, direction: str, amount: int, order: int = 0
) -> ListingPriceAdjustment:
    row = ListingPriceAdjustment(
        listing=listing, label=label, direction=direction, amount_minor=amount, sort_order=order
    )
    row.full_clean()
    row.save()
    return row


def test_adjustments_come_in_their_order(kelly: ProductModel) -> None:
    listing = listing_for(kelly)
    adjust(listing, "Complete set", "add", 30_000, order=2)
    adjust(listing, "Condition", "subtract", 45_000, order=1)

    rows = price_explainer(listing, today=TODAY)["adjustments"]

    assert [(r.label, r.direction, r.amount.amount_minor) for r in rows] == [
        ("Condition", "subtract", 45_000),
        ("Complete set", "add", 30_000),
    ]


@pytest.mark.parametrize(
    ("field", "value"),
    [("amount_minor", 0), ("label", ""), ("label", "x" * 81), ("direction", "times")],
)
def test_an_adjustment_needs_a_label_a_direction_and_an_amount(
    kelly: ProductModel, field: str, value: Any
) -> None:
    listing = listing_for(kelly)
    fields = {"label": "Condition", "direction": "subtract", "amount_minor": 45_000, field: value}

    with pytest.raises(ValidationError) as refused:
        ListingPriceAdjustment(listing=listing, **fields).full_clean()

    assert field in refused.value.message_dict


@pytest.mark.parametrize(("field", "value"), [("amount_minor", 0), ("direction", "times")])
def test_the_database_refuses_a_bad_adjustment(kelly: ProductModel, field: str, value: Any) -> None:
    row = adjust(listing_for(kelly), "Condition", "subtract", 45_000)

    with pytest.raises(IntegrityError), transaction.atomic():
        ListingPriceAdjustment.objects.filter(pk=row.pk).update(**{field: value})


# ---------- adjustments in the admin ----------


CHANGE = "/admin/listings/listing/{}/change/"


def form(listing: Listing, *rows: dict[str, str], initial: int = 0) -> dict[str, str]:
    """The listing change form with its two inlines, as the browser sends it."""
    data = {
        "ask_minor": str(listing.ask_minor),
        "price_changes-TOTAL_FORMS": "0",
        "price_changes-INITIAL_FORMS": "0",
        "price_adjustments-TOTAL_FORMS": str(len(rows)),
        "price_adjustments-INITIAL_FORMS": str(initial),
    }
    for index, row in enumerate(rows):
        data.update({f"price_adjustments-{index}-{key}": value for key, value in row.items()})
    return data


@pytest.fixture
def admin_client(client: Client) -> Client:
    admin_login(client, make_admin())
    return client


def test_staff_add_and_remove_adjustments_and_each_is_audited(admin_client: Client) -> None:
    listing = make_listing()
    url = CHANGE.format(listing.pk)

    response = admin_client.post(
        url,
        form(
            listing,
            {
                "label": "Condition",
                "direction": "subtract",
                "amount_minor": "450.00",
                "sort_order": "1",
            },
            {
                "label": "Complete set",
                "direction": "add",
                "amount_minor": "300.00",
                "sort_order": "2",
            },
        ),
    )

    assert response.status_code == 302, response.content.decode()[:3000]
    assert listing.price_adjustments.count() == 2
    created = AuditEvent.objects.filter(action="listings.listingpriceadjustment.created")
    assert created.count() == 2

    condition = listing.price_adjustments.get(label="Condition")
    complete = listing.price_adjustments.get(label="Complete set")
    admin_client.post(
        url,
        form(
            listing,
            {
                "id": str(condition.pk),
                "listing": str(listing.pk),
                "label": "Condition",
                "direction": "subtract",
                "amount_minor": "400.00",
                "sort_order": "1",
            },
            {
                "id": str(complete.pk),
                "listing": str(listing.pk),
                "label": "Complete set",
                "direction": "add",
                "amount_minor": "300.00",
                "sort_order": "2",
                "DELETE": "on",
            },
            initial=2,
        ),
    )

    assert list(listing.price_adjustments.values_list("label", "amount_minor")) == [
        ("Condition", 40_000)
    ]
    changed = AuditEvent.objects.get(action="listings.listingpriceadjustment.changed")
    assert changed.changes == {"amount_minor": {"from": 45_000, "to": 40_000}}
    assert AuditEvent.objects.filter(action="listings.listingpriceadjustment.deleted").count() == 1


def test_a_closed_listings_adjustments_cannot_change(admin_client: Client) -> None:
    listing = make_live_listing()
    adjust(listing, "Condition", "subtract", 45_000)
    services.withdraw_listing(listing, by=make_admin())

    response = admin_client.post(
        CHANGE.format(listing.pk),
        form(listing, {"label": "Extra", "direction": "add", "amount_minor": "1"}),
    )

    assert response.status_code == 403
    assert list(listing.price_adjustments.values_list("label", flat=True)) == ["Condition"]


# ---------- in the API ----------


def test_the_listing_page_carries_the_explainer(client: Client, kelly: ProductModel) -> None:
    listing = listing_for(kelly)
    make_sale(
        1_450_000,
        product_model=kelly,
        condition_grade="excellent",
        source="auction",
        sold_on=date.today(),
    )
    adjust(listing, "Complete set", "add", 30_000)

    body = client.get(f"{LISTINGS}{listing.pk}/").json()

    explainer = body["price_explainer"]
    assert explainer["recent_sales"]["grade"] == "excellent"
    assert explainer["recent_sales"]["count"] == 1
    assert explainer["recent_sales"]["low"] == money(1_450_000)
    assert explainer["recent_sales"]["median"] == money(1_450_000)
    assert explainer["recent_sales"]["sales"] == [
        {"sold_on": date.today().isoformat(), "price": money(1_450_000), "source": "auction"}
    ]
    assert explainer["adjustments"] == [
        {"label": "Complete set", "direction": "add", "amount": money(30_000)}
    ]
    assert "source_url" not in str(explainer)  # staff research links stay staff only


def test_with_nothing_to_explain_the_page_gets_empty_parts(client: Client) -> None:
    listing = make_live_listing()

    body = client.get(f"{LISTINGS}{listing.pk}/").json()

    assert body["price_explainer"] == {"recent_sales": None, "adjustments": []}


def test_shop_cards_do_not_carry_the_explainer(client: Client, kelly: ProductModel) -> None:
    listing_for(kelly)

    [card] = client.get(LISTINGS).json()["results"]

    assert "price_explainer" not in card


def test_the_listing_page_costs_a_fixed_number_of_queries(
    client: Client, kelly: ProductModel
) -> None:
    listing = listing_for(kelly)
    with CaptureQueriesContext(connection) as plain:
        client.get(f"{LISTINGS}{listing.pk}/")

    for days in range(1, 8):
        sale(kelly, 1_000_000 + days, days)
    for order in range(3):
        adjust(listing, f"Reason {order}", "add", 100 + order, order)
    with CaptureQueriesContext(connection) as busy:
        client.get(f"{LISTINGS}{listing.pk}/")

    assert len(busy) == len(plain)
