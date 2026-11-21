"""Small helpers that make catalog rows for tests.

Each helper fills in sensible defaults, so a test only names what it cares about.
"""

from typing import Any

from django.utils.text import slugify

from apps.catalog.models import Brand, Category, Material, ProductModel


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
