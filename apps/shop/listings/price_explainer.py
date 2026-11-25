"""The piece page's price explainer (build E8).

Two parts, both shown under the asking price:

``recent_sales``
    What the same design, at the same grade, sold for recently: comparable sales
    from the last ``COMPARABLE_SALES_DAYS`` days, newest first, at most
    ``COMPARABLE_SALES_SHOWN``. The range and the median use the sales shown, so the
    numbers always match the list on the page. A piece without a design is compared
    with sales of the same brand and category. ``None`` when the piece has no grade or
    nothing matches; the page then hides the section.
``adjustments``
    The staff's own lines ("Complete set, +$300"), in their order.

Comparing the asking price with the median ("1% under") is the page's job: it has both.
Where each sale was found (``source_url``) is staff research and is never included.
"""

from datetime import date, timedelta
from typing import Any, TypedDict

from django.conf import settings
from django.utils import timezone

from apps.inventory.catalog.models import ComparableSale
from apps.platform.core.money import Money
from apps.shop.listings.models import Listing, ListingPriceAdjustment


class Sale(TypedDict):
    sold_on: date
    price: Money
    source: str


class RecentSales(TypedDict):
    grade: str
    days: int
    count: int
    low: Money
    high: Money
    median: Money
    sales: list[Sale]


class PriceExplainer(TypedDict):
    recent_sales: RecentSales | None
    adjustments: list[ListingPriceAdjustment]


def median_minor(prices: list[int]) -> int:
    """The middle price; with an even count, halfway between the two middle ones,
    rounded half up to the cent."""
    ordered = sorted(prices)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle] + 1) // 2


def recent_sales(listing: Listing, *, today: date | None = None) -> RecentSales | None:
    piece = listing.piece
    if not piece.condition_grade:
        return None
    days: int = settings.COMPARABLE_SALES_DAYS
    since = (today or timezone.localdate()) - timedelta(days=days)
    matches: dict[str, Any] = {"condition_grade": piece.condition_grade, "sold_on__gte": since}
    if piece.product_model_id is not None:
        matches["product_model_id"] = piece.product_model_id
    else:
        matches.update(brand_id=piece.brand_id, category_id=piece.category_id)
    rows = list(
        ComparableSale.objects.filter(**matches)
        .order_by("-sold_on", "-id")
        .values("sold_on", "price_minor", "currency", "source")[: settings.COMPARABLE_SALES_SHOWN]
    )
    if not rows:
        return None
    prices = [row["price_minor"] for row in rows]
    currency = rows[0]["currency"]  # comparable sales are always USD
    return {
        "grade": piece.condition_grade,
        "days": days,
        "count": len(rows),
        "low": Money(min(prices), currency),
        "high": Money(max(prices), currency),
        "median": Money(median_minor(prices), currency),
        "sales": [
            {
                "sold_on": row["sold_on"],
                "price": Money(row["price_minor"], row["currency"]),
                "source": row["source"],
            }
            for row in rows
        ],
    }


def price_explainer(listing: Listing, *, today: date | None = None) -> PriceExplainer:
    """Both parts for one listing. Uses ``price_adjustments`` if it was prefetched."""
    return {
        "recent_sales": recent_sales(listing, today=today),
        "adjustments": list(listing.price_adjustments.all()),
    }
