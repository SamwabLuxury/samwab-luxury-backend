"""Small helpers that make catalog rows for tests.

Each helper fills in sensible defaults, so a test only names what it cares about.
"""

from datetime import date
from typing import Any

from django.utils.text import slugify

from apps.inventory.catalog.models import (
    Brand,
    CaptureProtocol,
    CaptureShot,
    Category,
    ComparableSale,
    Material,
    ProductModel,
)


def make_brand(name: str = "Hermès", **fields: Any) -> Brand:
    fields.setdefault("slug", slugify(name))
    return Brand.objects.create(name=name, **fields)


def make_category(name: str = "Bags", **fields: Any) -> Category:
    fields.setdefault("slug", slugify(name))
    return Category.objects.create(name=name, **fields)


def make_product_model(
    name: str = "Kelly 28",
    brand: Brand | None = None,
    category: Category | None = None,
    **fields: Any,
) -> ProductModel:
    fields.setdefault("slug", slugify(name))
    return ProductModel.objects.create(
        name=name,
        brand=brand or make_brand(),
        category=category or make_category(),
        **fields,
    )


def make_material(name: str = "Togo leather", **fields: Any) -> Material:
    return Material.objects.create(name=name, **fields)


def make_protocol(
    category: Category | None = None, version: int = 1, **fields: Any
) -> CaptureProtocol:
    return CaptureProtocol.objects.create(
        category=category or make_category(), version=version, **fields
    )


def make_shot(protocol: CaptureProtocol, code: str = "heat_stamp", **fields: Any) -> CaptureShot:
    fields.setdefault("name", code.replace("_", " ").capitalize())
    fields.setdefault("instrument", "phone")
    fields.setdefault("sort_order", 1)
    return CaptureShot.objects.create(protocol=protocol, code=code, **fields)


def make_sale(price_minor: int = 1_420_000, **fields: Any) -> ComparableSale:
    if "product_model" in fields:
        design = fields["product_model"]
        fields.setdefault("brand", design.brand)
        fields.setdefault("category", design.category)
    if "brand" not in fields:
        fields["brand"] = make_brand()
    if "category" not in fields:
        fields["category"] = make_category()
    fields.setdefault("source", "auction")
    fields.setdefault("sold_on", date(2026, 10, 1))
    return ComparableSale.objects.create(price_minor=price_minor, **fields)
