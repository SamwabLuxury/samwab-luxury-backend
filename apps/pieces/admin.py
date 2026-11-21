"""Piece screens for staff: register house stock and consigned pieces, and fix their details.

Statuses are shown but never edited here: they move only through the state
machine (``services.move_custody`` and ``services.set_verification``). Saves go
through the piece services, which record audit events; a change to the materials
is recorded as one event on the piece.
"""

from typing import Any

from django.contrib import admin
from django.http import HttpRequest

from apps.accounts.models import User
from apps.pieces import services
from apps.pieces.models import Piece, PieceMaterial


class PieceMaterialInline(admin.TabularInline):  # type: ignore[type-arg]
    model = PieceMaterial
    extra = 1
    autocomplete_fields = ("material",)
    verbose_name = "material"
    verbose_name_plural = "materials"


@admin.register(Piece)
class PieceAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = (
        "title",
        "brand",
        "category",
        "source",
        "verification_status",
        "custody_status",
        "current_owner",
    )
    list_filter = ("source", "verification_status", "custody_status", "category", "brand")
    list_select_related = ("brand", "category", "category__parent", "current_owner")
    search_fields = ("title", "brand__name", "product_model__name", "serial_or_date_code")
    autocomplete_fields = ("brand", "category", "product_model", "current_owner")
    inlines = (PieceMaterialInline,)
    readonly_fields = ("verification_status", "custody_status", "created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("title", "brand", "category", "product_model", "description")}),
        (
            "Details",
            {
                "fields": (
                    "department",
                    "size_system",
                    "size_label",
                    "production_year",
                    "condition_grade",
                    "attributes",
                )
            },
        ),
        (
            "Origin and ownership",
            {
                "fields": (
                    "source",
                    "current_owner",
                    "home_country",
                    "acquisition_cost_minor",
                    "authentication_basis",
                )
            },
        ),
        ("Staff only", {"fields": ("serial_or_date_code", "hs_code", "storage_free_until")}),
        (
            "Status",
            {"fields": ("verification_status", "custody_status", "created_at", "updated_at")},
        ),
    )

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def save_model(self, request: HttpRequest, obj: Any, form: Any, change: bool) -> None:
        staff: User = request.user  # type: ignore[assignment]
        # The materials are saved after the piece (in save_related); remember them first.
        obj._materials_before = services.material_names(obj) if change else []
        if change:
            services.update_piece(obj, by=staff)
        else:
            services.register_piece(obj, by=staff)

    def save_related(self, request: HttpRequest, form: Any, formsets: Any, change: bool) -> None:
        super().save_related(request, form, formsets, change)
        staff: User = request.user  # type: ignore[assignment]
        piece = form.instance
        services.record_materials(piece, before=piece._materials_before, by=staff)
