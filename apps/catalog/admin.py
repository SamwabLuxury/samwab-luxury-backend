"""The catalog manager: staff add, rename, reorder and retire catalog rows here.

Brands, categories and designs are retired, never deleted. A slug is set once,
when the row is created, because the web app's links use it. Every save, delete
and inline row goes through the catalog service, which records an audit event.
"""

from typing import Any

from django.contrib import admin, messages
from django.contrib.admin import ActionLocation
from django.db import models
from django.db.models import QuerySet
from django.http import HttpRequest

from apps.accounts.models import User
from apps.audit import services as audit
from apps.catalog import services
from apps.catalog.models import (
    Brand,
    CaptureProtocol,
    CaptureShot,
    Category,
    ComparableSale,
    Material,
    ProductModel,
)
from apps.core.exceptions import AppError


class CatalogAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """Every catalog screen saves through the catalog service."""

    def save_model(self, request: HttpRequest, obj: Any, form: Any, change: bool) -> None:
        services.save_entry(obj, by=_staff(request))

    def delete_model(self, request: HttpRequest, obj: Any) -> None:
        services.delete_entry(obj, by=_staff(request))

    def delete_queryset(self, request: HttpRequest, queryset: QuerySet[Any]) -> None:
        services.delete_entries(queryset, by=_staff(request))


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


# ---------- capture protocols ----------


class CaptureShotInline(admin.TabularInline):  # type: ignore[type-arg]
    """The shots of a protocol. They can change only while the protocol is a draft."""

    model = CaptureShot
    extra = 0
    fields = (
        "sort_order",
        "code",
        "name",
        "kind",
        "instrument",
        "magnification",
        "is_required",
        "instructions",
    )

    @staticmethod
    def _open(protocol: CaptureProtocol | None) -> bool:
        return protocol is None or protocol.is_draft

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return self._open(obj) and super().has_add_permission(request, obj)

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return self._open(obj) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return self._open(obj) and super().has_delete_permission(request, obj)


@admin.register(CaptureProtocol)
class CaptureProtocolAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """Write a draft, add its shots, then activate it. To change an active one, make a new draft."""

    list_display = ("__str__", "category", "product_model", "version", "status")
    list_filter = ("status", "category")
    list_select_related = ("category", "category__parent", "product_model__brand")
    search_fields = ("category__name", "product_model__name", "product_model__brand__name")
    autocomplete_fields = ("category", "product_model")
    fields = ("category", "product_model", "version", "status")
    readonly_fields = ("version", "status")
    inlines = (CaptureShotInline,)
    actions = ("activate_selected", "retire_selected", "new_draft_selected")

    def get_readonly_fields(self, request: HttpRequest, obj: Any = None) -> Any:
        if obj is None:
            return self.readonly_fields
        return ("category", "product_model", *self.readonly_fields)

    def get_actions(
        self, request: HttpRequest, action_location: Any = ActionLocation.CHANGE_LIST
    ) -> Any:
        # Django 6.1 signature: actions can also sit on the change form.
        actions = super().get_actions(request, action_location=action_location)
        actions.pop("delete_selected", None)  # deleting is for drafts only, one at a time
        return actions

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        if obj is not None and not obj.is_draft:
            return False
        return super().has_delete_permission(request, obj)

    def save_model(self, request: HttpRequest, obj: Any, form: Any, change: bool) -> None:
        if not change:
            services.add_protocol(obj, by=_staff(request))
        # A saved protocol has no fields to change here: only its shots, saved with the inline.

    def save_formset(self, request: HttpRequest, form: Any, formset: Any, change: bool) -> None:
        audit.save_inline_rows(formset, by=_staff(request))

    def delete_model(self, request: HttpRequest, obj: Any) -> None:
        services.delete_protocol(obj, by=_staff(request))

    def _each(
        self, request: HttpRequest, queryset: QuerySet[CaptureProtocol], step: Any, done: str
    ) -> None:
        for protocol in queryset:
            try:
                result = step(protocol, by=_staff(request))
            except AppError as error:
                self.message_user(request, f"{protocol.label}: {error.message}", messages.ERROR)
            else:
                self.message_user(request, done.format(protocol=protocol, result=result))

    @admin.action(description="Activate the selected drafts")
    def activate_selected(self, request: HttpRequest, queryset: QuerySet[CaptureProtocol]) -> None:
        self._each(request, queryset, services.activate_protocol, "Activated {protocol.label}.")

    @admin.action(description="Retire the selected protocols")
    def retire_selected(self, request: HttpRequest, queryset: QuerySet[CaptureProtocol]) -> None:
        self._each(request, queryset, services.retire_protocol, "Retired {protocol.label}.")

    @admin.action(description="Make a new draft version of the selected protocols")
    def new_draft_selected(self, request: HttpRequest, queryset: QuerySet[CaptureProtocol]) -> None:
        self._each(request, queryset, services.new_draft_from, "Made {result}.")


# ---------- comparable sales ----------


@admin.register(ComparableSale)
class ComparableSaleAdmin(CatalogAdmin):
    list_display = ("sold_on", "brand", "product_model", "category", "price", "source")
    list_filter = ("source", "category", "brand")
    list_select_related = ("brand", "category", "category__parent", "product_model__brand")
    search_fields = ("brand__name", "product_model__name", "size_label")
    autocomplete_fields = ("brand", "category", "product_model")
    date_hierarchy = "sold_on"
    fields = (
        "brand",
        "category",
        "product_model",
        "department",
        "size_label",
        "condition_grade",
        "price_minor",
        "sold_on",
        "source",
        "source_url",
    )
