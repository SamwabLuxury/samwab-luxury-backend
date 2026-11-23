from django.urls import path

from apps.inventory.catalog.api.views import BrandListView, CategoryListView, ProductModelListView

app_name = "catalog"

urlpatterns = [
    path("brands/", BrandListView.as_view(), name="brands"),
    path("categories/", CategoryListView.as_view(), name="categories"),
    path("product-models/", ProductModelListView.as_view(), name="product-models"),
]
