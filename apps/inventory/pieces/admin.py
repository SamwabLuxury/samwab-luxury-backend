"""Piece screens for staff: register house stock and consigned pieces, and fix their details.

Statuses are shown but never edited here: they move only through the state
machine (``services.move_custody`` and ``services.set_verification``). Saves go
through the piece services, which record audit events; a change to the materials
is recorded as one event on the piece.

Photos are added on the piece's page. Each upload is checked and cleaned by
``photos.prepare`` while the form is validated, so a refused file shows its
message on the form; saving goes through ``services.add_photo``, ``update_photo``
and ``delete_photo``.
"""

from typing import Any, ClassVar

from django import forms
from django.contrib import admin, messages
from django.contrib.admin import ActionLocation
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils.html import format_html

from apps.inventory.pieces import photos, services
from apps.inventory.pieces.enums import CustodyStatus, VerificationStatus
from apps.inventory.pieces.models import Media, Piece, PieceMaterial
from apps.platform.core.admin_dollars import DollarsAdmin
from apps.platform.core.admin_look import ModelAdmin, TabularInline
from apps.platform.core.exceptions import AppError
from apps.platform.core.storage import PhotoStorageError
from apps.users.accounts.models import User


class PieceMaterialInline(TabularInline):  # type: ignore[type-arg]
    model = PieceMaterial
    extra = 1
    autocomplete_fields = ("material",)
    verbose_name = "material"
    verbose_name_plural = "materials"


class PhotoForm(forms.ModelForm):  # type: ignore[type-arg]
    upload = forms.FileField(required=False, label="Photo")
    # New photos always go last; the order is for moving saved ones.
    sort_order = forms.IntegerField(required=False, min_value=0, max_value=32767, label="order")

    class Meta:
        model = Media
        fields = ("kind", "sort_order", "label", "caption")
        labels: ClassVar[dict[str, str]] = {
            "label": "name (optional)",
            "caption": "note (optional)",
        }
        widgets: ClassVar[dict[str, forms.Widget]] = {
            "label": forms.TextInput(attrs={"size": 14, "placeholder": "Stamp"}),
            "caption": forms.Textarea(attrs={"rows": 2, "cols": 32}),
        }

    def clean(self) -> dict[str, Any]:
        data: dict[str, Any] = super().clean() or {}
        upload = data.get("upload")
        if self.instance._state.adding:
            if upload is None:
                self.add_error("upload", "Choose a photo to upload.")
            else:
                try:
                    self.prepared = photos.prepare(upload)
                except photos.PhotoRejectedError as refused:
                    self.add_error("upload", refused.message)
        elif upload is not None:
            self.add_error("upload", "To use another picture, delete this photo and add a new one.")
        return data


class PhotoInline(TabularInline):  # type: ignore[type-arg]
    model = Media
    form = PhotoForm
    extra = 1
    fields = ("preview", "upload", "kind", "sort_order", "label", "caption")
    readonly_fields = ("preview",)
    verbose_name = "photo"
    verbose_name_plural = "photos (JPEG, PNG or WebP; location data is removed)"

    @admin.display(description="preview")
    def preview(self, media: Media) -> str:
        if media._state.adding:  # a new row: nothing uploaded yet
            return "-"
        return format_html('<img src="{}" alt="" style="height:80px">', media.file.url)


@admin.register(Piece)
class PieceAdmin(DollarsAdmin, ModelAdmin):  # type: ignore[type-arg]
    dollar_fields = (("acquisition_cost_minor", "What we paid for it"),)
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
    inlines = (PieceMaterialInline, PhotoInline)
    readonly_fields = ("verification_status", "custody_status", "created_at", "updated_at")
    actions = (
        "mark_in_transit",
        "mark_received",
        "put_in_vault",
        "verify_selected",
        "mark_not_authentic_selected",
    )
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

    def get_actions(
        self, request: HttpRequest, action_location: Any = ActionLocation.CHANGE_LIST
    ) -> Any:
        actions = super().get_actions(request, action_location=action_location)
        actions.pop("delete_selected", None)  # pieces are never deleted
        return actions

    # ---------- custody moves (E7a) ----------
    # Until the custody build (16) records custody events with a site, a shelf and a
    # seal number, staff move a piece along its path here. Each step goes through
    # ``services.move_custody``: the state machine checks it and the audit log keeps it.

    @admin.action(description="Mark on its way to the vault", permissions=["change"])
    def mark_in_transit(self, request: HttpRequest, queryset: QuerySet[Piece]) -> None:
        self._move(request, queryset, CustodyStatus.IN_TRANSIT, "is on its way to the vault")

    @admin.action(description="Received at intake", permissions=["change"])
    def mark_received(self, request: HttpRequest, queryset: QuerySet[Piece]) -> None:
        self._move(request, queryset, CustodyStatus.AT_INTAKE, "was received at intake")

    @admin.action(description="Put in the vault", permissions=["change"])
    def put_in_vault(self, request: HttpRequest, queryset: QuerySet[Piece]) -> None:
        self._move(request, queryset, CustodyStatus.IN_VAULT, "is in the vault")

    def _move(self, request: HttpRequest, queryset: QuerySet[Piece], to: str, done: str) -> None:
        staff: User = request.user  # type: ignore[assignment]
        for piece in queryset:
            if to == CustodyStatus.IN_TRANSIT and piece.custody_status != CustodyStatus.WITH_OWNER:
                # A piece leaving the vault is a sale handed to a courier: orders do that.
                refused = "only a piece still with its owner can be marked on its way to the vault."
                self.message_user(request, f"{piece}: {refused}", messages.ERROR)
                continue
            try:
                services.move_custody(piece, to=to, by=staff)
            except AppError:
                self.message_user(request, f"{piece}: {_why_not(piece)}", messages.ERROR)
            else:
                self.message_user(request, f"{piece} {done}.")

    # ---------- the check result (build 15) ----------
    # Verifying issues the piece's passport in the same step (passports app). Only
    # people allowed to verify (the reviewer role) see these two actions.

    def has_verify_permission(self, request: HttpRequest) -> bool:
        return request.user.has_perm("passports.verify_passport")

    @admin.action(description="Verified authentic: issue the passport", permissions=["verify"])
    def verify_selected(self, request: HttpRequest, queryset: QuerySet[Piece]) -> None:
        from apps.inventory.passports import services as passports

        staff: User = request.user  # type: ignore[assignment]
        for piece in queryset:
            if self._result_already_recorded(request, piece):
                continue
            passport = passports.verify(piece, by=staff)
            self.message_user(request, f"{piece} is verified: passport {passport} issued.")

    @admin.action(description="Not authentic", permissions=["verify"])
    def mark_not_authentic_selected(self, request: HttpRequest, queryset: QuerySet[Piece]) -> None:
        from apps.inventory.passports import services as passports

        staff: User = request.user  # type: ignore[assignment]
        for piece in queryset:
            if self._result_already_recorded(request, piece):
                continue
            passports.mark_not_authentic(piece, by=staff)
            self.message_user(request, f"{piece} is recorded as not authentic.", messages.WARNING)

    def _result_already_recorded(self, request: HttpRequest, piece: Piece) -> bool:
        if piece.verification_status == VerificationStatus.UNVERIFIED:
            return False
        shown = piece.get_verification_status_display().lower()
        self.message_user(
            request,
            f"{piece}: the check result is already recorded ({shown}) and cannot change.",
            messages.ERROR,
        )
        return True

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

    def save_formset(self, request: HttpRequest, form: Any, formset: Any, change: bool) -> None:
        if formset.model is not Media:
            super().save_formset(request, form, formset, change)
            return
        staff: User = request.user  # type: ignore[assignment]
        # The admin writes its history from these lists, which formset.save() would fill.
        formset.new_objects, formset.changed_objects, formset.deleted_objects = [], [], []
        for photo_form in formset.deleted_forms:
            if photo_form.instance.pk:
                services.delete_photo(photo_form.instance, by=staff)
                formset.deleted_objects.append(photo_form.instance)
        for photo_form in formset.initial_forms:
            if photo_form not in formset.deleted_forms and photo_form.has_changed():
                data = photo_form.cleaned_data
                order = data["sort_order"]
                services.update_photo(
                    photo_form.instance,
                    kind=data["kind"],
                    sort_order=photo_form.initial["sort_order"] if order is None else order,
                    label=data.get("label", ""),
                    caption=data.get("caption", ""),
                    by=staff,
                )
                formset.changed_objects.append((photo_form.instance, photo_form.changed_data))
        for photo_form in formset.extra_forms:
            if photo_form not in formset.deleted_forms and photo_form.has_changed():
                try:
                    media = services.add_photo(
                        form.instance,
                        photo_form.prepared,
                        kind=photo_form.cleaned_data["kind"],
                        label=photo_form.cleaned_data.get("label", ""),
                        caption=photo_form.cleaned_data.get("caption", ""),
                        by=staff,
                    )
                except PhotoStorageError:
                    # Photo storage (Cloudinary) is down: the piece is saved, this photo is not.
                    self.message_user(
                        request,
                        "A photo could not be saved because photo storage did not answer. "
                        "Add it again in a moment.",
                        messages.ERROR,
                    )
                    continue
                formset.new_objects.append(media)


_NEXT_STEP = {
    CustodyStatus.WITH_OWNER: "it is with its owner. First: Mark on its way to the vault.",
    CustodyStatus.IN_TRANSIT: "it is on its way. First: Received at intake.",
    CustodyStatus.AT_INTAKE: "it is at intake. Next: Put in the vault.",
    CustodyStatus.IN_VAULT: "it is already in the vault.",
    CustodyStatus.WITH_BUYER: "it is with its buyer.",
}


def _why_not(piece: Piece) -> str:
    """A refused custody step in plain words, naming the step needed first."""
    return _NEXT_STEP[CustodyStatus(piece.custody_status)]
