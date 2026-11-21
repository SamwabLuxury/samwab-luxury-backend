"""The catalog manager: staff add, rename, reorder and retire catalog rows here.

Brands, categories and designs are retired, never deleted. A slug is set once,
when the row is created, because the web app's links use it.
"""

from typing import Any

from django.contrib import admin
from django.db import models
from django.db.models import QuerySet
from django.http import HttpRequest

from apps.accounts.models import User
from apps.catalog import services
from apps.catalog.models import Brand, Category, Material, ProductModel


class CatalogAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """Every catalog screen saves through the catalog service."""

    def save_model(self, request: HttpRequest, obj: Any, form: Any, change: bool) -> None:
        services.save_entry(obj, by=_staff(request))


class SluggedAdmin(CatalogAdmin):
    """The slug is filled in from the name when the row is created, then never changes."""

    slug_from: tuple[str, ...] = ("name",)

    def get_readonly_fields(self, request: HttpRequest, obj: Any = None) -> Any:
        fields = tuple(super().get_readonly_fields(request, obj))
        return (*fields, "slug") if obj is not None else fields

    def get_prepopulated_fields(self, request: HttpRequest, obj: Any = None) -> dict[str, Any]:
        return {"slug": self.slug_from} if obj is None else {}


class RetireOnlyAdmin(SluggedAdmin):
    """For rows other rows depend on: retire and bring back, never delete."""

    actions = ("retire_selected", "restore_selected")

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    @admin.action(description="Retire the selected rows")
    def retire_selected(self, request: HttpRequest, queryset: QuerySet[models.Model]) -> None:
        changed = services.set_active(queryset, is_active=False, by=_staff(request))
        self.message_user(request, f"Retired {changed}.")

    @admin.action(description="Bring back the selected rows")
    def restore_selected(self, request: HttpRequest, queryset: QuerySet[models.Model]) -> None:
        changed = services.set_active(queryset, is_active=True, by=_staff(request))
        self.message_user(request, f"Brought back {changed}.")


def _staff(request: HttpRequest) -> User:
    user: User = request.user  # type: ignore[assignment]
    return user


@admin.register(Brand)
class BrandAdmin(RetireOnlyAdmin):
    list_display = ("name", "slug", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    fields = ("name", "slug", "is_active")


@admin.register(Category)
class CategoryAdmin(RetireOnlyAdmin):
    list_display = ("name", "parent", "slug", "sort_order", "is_active")
    list_editable = ("sort_order", "is_active")
    list_filter = ("is_active", "parent")
    list_select_related = ("parent",)
    search_fields = ("name", "slug")
    autocomplete_fields = ("parent",)
    fields = (
        "name",
        "slug",
        "parent",
        "sort_order",
        "is_active",
        "default_storage",
        "default_hs_code",
        "attribute_schema",
        "flaw_types",
        "updated_by",
        "updated_at",
    )
    readonly_fields = ("updated_by", "updated_at")


@admin.register(ProductModel)
class ProductModelAdmin(RetireOnlyAdmin):
    list_display = ("name", "brand", "category", "department", "era_from", "era_to", "is_active")
    list_filter = ("is_active", "department", "brand", "category")
    list_select_related = ("brand", "category")
    search_fields = ("name", "slug", "brand__name")
    autocomplete_fields = ("brand", "category")
    fields = (
        "brand",
        "category",
        "name",
        "slug",
        "department",
        "era_from",
        "era_to",
        "attribute_schema",
        "is_active",
    )


@admin.register(Material)
class MaterialAdmin(CatalogAdmin):
    """Materials have no retire switch in the data model. A typo can be deleted; once
    pieces use a material (build 14), the database refuses to delete it."""

    list_display = ("name", "is_exotic", "domestic_only", "cites_listed", "sale_restricted")
    list_filter = ("is_exotic", "domestic_only", "cites_listed", "sale_restricted")
    search_fields = ("name",)
    fields = (
        "name",
        "is_exotic",
        "domestic_only",
        "cites_listed",
        "sale_restricted",
        "restriction_note",
    )
