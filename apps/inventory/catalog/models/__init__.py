"""The catalog's tables, one module per subject. Import them from here.

- ``catalog``: brands, categories, named designs (product models) and materials.
- ``capture``: the photo and reading protocols staff follow for each category or design.
- ``comparables``: past sales that feed the fair-price explainer.
"""

from apps.inventory.catalog.models.capture import CaptureProtocol, CaptureShot
from apps.inventory.catalog.models.catalog import Brand, Category, Material, ProductModel
from apps.inventory.catalog.models.comparables import ComparableSale

__all__ = [
    "Brand",
    "CaptureProtocol",
    "CaptureShot",
    "Category",
    "ComparableSale",
    "Material",
    "ProductModel",
]
