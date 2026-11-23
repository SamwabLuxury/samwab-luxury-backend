from rest_framework import serializers

from apps.inventory.catalog.models import Brand, Category, ProductModel


class BrandSerializer(serializers.ModelSerializer[Brand]):
    class Meta:
        model = Brand
        fields = ("id", "name", "slug")


class CategorySerializer(serializers.ModelSerializer[Category]):
    parent_id = serializers.UUIDField(
        allow_null=True, read_only=True, help_text="The category this one sits under."
    )

    class Meta:
        model = Category
        fields = ("id", "parent_id", "name", "slug", "attribute_schema")


class ProductModelSerializer(serializers.ModelSerializer[ProductModel]):
    brand_id = serializers.UUIDField(read_only=True)
    category_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = ProductModel
        fields = ("id", "brand_id", "category_id", "name", "slug", "era_from", "era_to")


class ProductModelFilterSerializer(serializers.Serializer[None]):
    """The query parameters of ``GET /api/v1/product-models/``. Empty means no filter."""

    brand = serializers.SlugField(
        required=False, allow_blank=True, max_length=160, help_text="A brand's slug."
    )
    category = serializers.SlugField(
        required=False, allow_blank=True, max_length=80, help_text="A category's slug."
    )
