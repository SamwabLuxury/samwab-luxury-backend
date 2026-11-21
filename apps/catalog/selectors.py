"""Reads of the catalog for the public API. Nothing here changes data.

Public lists show only what is active. A design is hidden when it, its brand
or its category is retired.

Categories and designs also get ``position``: one text value that is unique per row and
sorts in display order. The API pages on it, because a cursor needs a unique
value to stand on (see ``apps/core/api/pagination.py``).
"""

from django.db.models import CharField, QuerySet, Value
from django.db.models.functions import Cast, Concat, LPad

from apps.catalog.models import Brand, Category, ProductModel


def public_brands() -> QuerySet[Brand]:
    """Active brands. Slugs are unique, so the API pages on the slug itself."""
    return Brand.objects.filter(is_active=True)


def public_categories() -> QuerySet[Category]:
    """Active categories in menu order: lowest ``sort_order`` first, then by slug."""
    menu_number = LPad(Cast("sort_order", CharField()), 5, Value("0"))  # 7 -> "00007"
    return Category.objects.filter(is_active=True).annotate(
        position=Concat(menu_number, Value(":"), "slug", output_field=CharField())
    )


def public_product_models(
    *, brand_slug: str | None = None, category_slug: str | None = None
) -> QuerySet[ProductModel]:
    """Active designs, optionally for one brand and one category (by slug)."""
    designs = ProductModel.objects.filter(
        is_active=True, brand__is_active=True, category__is_active=True
    ).annotate(
        # Brands can share a design slug, so the ID makes the position unique.
        position=Concat("slug", Value(":"), Cast("id", CharField()), output_field=CharField())
    )
    if brand_slug:
        designs = designs.filter(brand__slug=brand_slug)
    if category_slug:
        designs = designs.filter(category__slug=category_slug)
    return designs
