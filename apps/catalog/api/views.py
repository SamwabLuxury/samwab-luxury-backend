"""Public catalog lists for the store's menus and filters. Anyone can read them."""

from typing import Any

from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny

from apps.catalog import selectors
from apps.catalog.api.serializers import (
    BrandSerializer,
    CategorySerializer,
    ProductModelFilterSerializer,
    ProductModelSerializer,
)
from apps.catalog.models import Brand, Category, ProductModel
from apps.core.api.pagination import ordered_by


class PublicListView(ListAPIView):  # type: ignore[type-arg]
    """A read-only list that needs no login and no session."""

    authentication_classes = ()
    permission_classes = (AllowAny,)


@extend_schema_view(
    get=extend_schema(
        summary="List brands",
        description="Active brands in alphabetical order (by slug).",
        operation_id="brands_list",
        tags=["Catalog"],
        auth=[],
    )
)
class BrandListView(PublicListView):
    serializer_class = BrandSerializer
    pagination_class = ordered_by("slug")

    def get_queryset(self) -> QuerySet[Brand]:
        return selectors.public_brands()


@extend_schema_view(
    get=extend_schema(
        summary="List categories",
        description="Active categories in menu order: lowest `sort_order` first, then by slug. "
        "`parent_id` places a category under another, so the web app can build the menu tree.",
        operation_id="categories_list",
        tags=["Catalog"],
        auth=[],
    )
)
class CategoryListView(PublicListView):
    serializer_class = CategorySerializer
    pagination_class = ordered_by("position")

    def get_queryset(self) -> QuerySet[Category]:
        return selectors.public_categories()


@extend_schema_view(
    get=extend_schema(
        summary="List named designs",
        description="Active designs, such as the Kelly 28, in order of slug. "
        "Filter with `brand` and `category` (their slugs). An unknown slug gives an empty list.",
        operation_id="product_models_list",
        tags=["Catalog"],
        auth=[],
        parameters=[ProductModelFilterSerializer],
    )
)
class ProductModelListView(PublicListView):
    serializer_class = ProductModelSerializer
    pagination_class = ordered_by("position")

    def get_queryset(self) -> QuerySet[ProductModel]:
        filters = ProductModelFilterSerializer(data=self.request.query_params)
        filters.is_valid(raise_exception=True)
        chosen: dict[str, Any] = filters.validated_data
        return selectors.public_product_models(
            brand_slug=chosen.get("brand"), category_slug=chosen.get("category")
        )
