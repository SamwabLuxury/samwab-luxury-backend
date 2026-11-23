"""Reads of listings for the public API. Nothing here changes data.

The public sees live listings only, and never a piece found not authentic.
"""

from django.db.models import Max, Prefetch, Q, QuerySet
from django.db.models.functions import Now

from apps.inventory.pieces.enums import ConditionGrade, VerificationStatus
from apps.inventory.pieces.models import Media
from apps.shop.listings.enums import ListingStatus
from apps.shop.listings.models import Listing

# Best first, as in the data model.
GRADES_BEST_FIRST = (
    ConditionGrade.NEW,
    ConditionGrade.EXCELLENT,
    ConditionGrade.VERY_GOOD,
    ConditionGrade.GOOD,
    ConditionGrade.FAIR,
)


def grades_at_least(lowest: str) -> list[str]:
    """``very_good`` gives new, excellent and very_good."""
    return [str(grade) for grade in GRADES_BEST_FIRST[: GRADES_BEST_FIRST.index(lowest) + 1]]


def public_listings(
    *,
    q: str = "",
    brand_slug: str = "",
    category_slug: str = "",
    condition_min: str = "",
    price_max: int | None = None,
) -> QuerySet[Listing]:
    """Live listings with their piece, catalog rows and photos, for browse and detail pages.

    ``category_slug`` also matches the categories one level under it, so "Jewellery"
    shows bracelets. Every word of ``q`` must appear in the title, brand or design.
    """
    listings = (
        Listing.objects.filter(status=ListingStatus.LIVE)
        .exclude(piece__verification_status=VerificationStatus.NOT_AUTHENTIC)
        .select_related("piece__brand", "piece__category", "piece__product_model")
        .prefetch_related(
            Prefetch("piece__photos", queryset=Media.objects.order_by("sort_order", "id"))
        )
        # Until when a buyer's checkout holds the piece (shown as reserved_until).
        .annotate(
            held_until=Max(
                "orders__hold_until",
                filter=Q(orders__status="pending_payment", orders__hold_until__gt=Now()),
            )
        )
    )
    if brand_slug:
        listings = listings.filter(piece__brand__slug=brand_slug)
    if category_slug:
        listings = listings.filter(
            Q(piece__category__slug=category_slug) | Q(piece__category__parent__slug=category_slug)
        )
    if condition_min:
        listings = listings.filter(piece__condition_grade__in=grades_at_least(condition_min))
    if price_max is not None:
        listings = listings.filter(ask_minor__lte=price_max)
    for word in q.split():
        listings = listings.filter(
            Q(piece__title__icontains=word)
            | Q(piece__brand__name__icontains=word)
            | Q(piece__product_model__name__icontains=word)
        )
    return listings
