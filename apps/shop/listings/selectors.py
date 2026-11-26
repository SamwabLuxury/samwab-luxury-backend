"""Reads of listings for the public API. Nothing here changes data.

The public sees live listings only, and never a piece found not authentic.
"""

from typing import Any

from django.db.models import Count, F, Max, OuterRef, Prefetch, Q, QuerySet, Subquery
from django.db.models.functions import Coalesce, Now

from apps.inventory.catalog.models import Category
from apps.inventory.pieces.enums import ConditionGrade, VerificationStatus
from apps.inventory.pieces.models import Media
from apps.shop.listings import drops
from apps.shop.listings.enums import ListingStatus
from apps.shop.listings.models import Drop, Listing, SavedListing
from apps.users.accounts.models import User

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
        _matching(
            q=q,
            brand_slug=brand_slug,
            category_slug=category_slug,
            condition_min=condition_min,
            price_max=price_max,
        )
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
    return listings


def _matching(
    *,
    q: str = "",
    brand_slug: str = "",
    category_slug: str = "",
    condition_min: str = "",
    price_max: int | None = None,
) -> QuerySet[Listing]:
    """The one place the shop's filters are applied: live, not found not authentic,
    and matching every filter given. Plain rows, so counting them stays cheap."""
    listings = Listing.objects.filter(status=ListingStatus.LIVE).exclude(
        piece__verification_status=VerificationStatus.NOT_AUTHENTIC
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


def saved_listings(user: User) -> QuerySet[Listing]:
    """The pieces a person saved that are still for sale, each with ``saved_at``.

    Built on ``visible_listings``, so a sold, withdrawn or not-authentic piece, or a
    drop lot she may not see yet, is left out, exactly as on the listing page.
    """
    saved_at = SavedListing.objects.filter(user=user, listing=OuterRef("pk")).values("created_at")[
        :1
    ]
    return (
        visible_listings(user).annotate(saved_at=Subquery(saved_at)).filter(saved_at__isnull=False)
    )


def shop_listings(**filters: Any) -> QuerySet[Listing]:
    """The normal shop: live listings not in a running drop (closed drops' lots are)."""
    return public_listings(**filters).filter(drops.in_normal_shop())


def shop_count(**filters: Any) -> int:
    """How many pieces the shop shows for these filters, on every page of the list."""
    return _matching(**filters).filter(drops.in_normal_shop()).count()


def shop_facets(**filters: Any) -> dict[str, Any]:
    """The total and a count per house and per top category, for the shop's filters.

    A house's count leaves out the brand filter, and a category's the category
    filter, so choosing Hermès still lists every house with its own count. A
    category under another (Bracelets) is counted in its top one (Jewellery), as the
    shop's category filter works. Houses and categories with nothing for sale are
    left out. Both lists are sorted by name.
    """
    in_shop = drops.in_normal_shop()
    brands = (
        _matching(**{**filters, "brand_slug": ""})
        .filter(in_shop)
        .values(slug=F("piece__brand__slug"), name=F("piece__brand__name"))
        .annotate(count=Count("id"))
        .order_by("name", "slug")
    )
    top = Coalesce("piece__category__parent", "piece__category")
    categories = (
        _matching(**{**filters, "category_slug": ""})
        .filter(in_shop)
        .annotate(top_id=top)
        .values("top_id")
        .annotate(count=Count("id"))
        .order_by()
    )
    names = {
        row["id"]: row
        for row in Category.objects.filter(id__in=[c["top_id"] for c in categories]).values(
            "id", "slug", "name"
        )
    }
    return {
        "total": shop_count(**filters),
        "brands": [dict(row) for row in brands],
        "categories": sorted(
            (
                {
                    "slug": names[c["top_id"]]["slug"],
                    "name": names[c["top_id"]]["name"],
                    "count": c["count"],
                }
                for c in categories
            ),
            key=lambda c: (c["name"], c["slug"]),
        ),
    }


def visible_listings(viewer: User | None) -> QuerySet[Listing]:
    """Live listings this person may open, drop lots included when their time has come."""
    return public_listings().filter(drops.visible_to(viewer))


def drops_with_counts() -> QuerySet[Drop]:
    return Drop.objects.annotate(lot_count=Count("lots"))


def running_drops() -> QuerySet[Drop]:
    """Drops not yet closed, soonest first, with how many lots each has."""
    return drops_with_counts().filter(closes_at__gt=Now()).order_by("public_at", "id")


def drop_lots(drop: Drop, viewer: User | None) -> QuerySet[Listing]:
    """The lots of a drop that this person may see now, in lot order. A closed drop
    shows none: its unsold lots are in the normal shop."""
    if drop.phase() == "closed":
        return Listing.objects.none()
    return (
        visible_listings(viewer)
        .filter(drop_lot__drop=drop)
        .select_related("drop_lot")
        .order_by("drop_lot__lot_number")
    )
