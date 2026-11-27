"""Passports, condition reports and restorations in the admin site.

Passports are issued by verifying a piece (an action on the piece list); here staff
only look them up and may hide one. Condition reports are added, never changed: a
new look at the piece is a new report. Flaws are typed one per line.
"""

from typing import Any

from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.http import HttpRequest

from apps.inventory.passports import services
from apps.inventory.passports.flaws import checked_flaws, parse_flaws
from apps.inventory.passports.models import ConditionReport, Passport, Restoration
from apps.platform.core.admin_dollars import DollarsAdmin, dollars_column
from apps.platform.core.admin_look import ModelAdmin
from apps.users.accounts.models import User

FLAW_HELP = (
    "One flaw per line: what | how bad | where | note. For example: "
    "corner_rub | minor | Base, front left | Light rubbing, does not affect use. "
    "How bad is minor, moderate or major. Leave empty when there are none."
)


def _staff(request: HttpRequest) -> User:
    user: User = request.user  # type: ignore[assignment]
    return user


@admin.register(Passport)
class PassportAdmin(ModelAdmin):  # type: ignore[type-arg]
    list_display = ("number", "piece", "public_code", "is_public", "created_at")
    list_filter = ("is_public",)
    search_fields = ("public_code", "piece__title")
    list_select_related = ("piece",)
    fields = ("number", "piece", "public_code", "is_public", "created_at")
    readonly_fields = ("number", "piece", "public_code", "created_at")

    @admin.display(description="Passport Nº", ordering="passport_number")
    def number(self, passport: Passport) -> str:
        return passport.printed_number

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False  # issued by verifying the piece

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def save_model(self, request: HttpRequest, obj: Any, form: Any, change: bool) -> None:
        services.set_public(obj, obj.is_public, by=_staff(request))


class ConditionReportForm(forms.ModelForm):  # type: ignore[type-arg]
    flaw_lines = forms.CharField(
        label="Flaws", required=False, widget=forms.Textarea(attrs={"rows": 6}), help_text=FLAW_HELP
    )

    class Meta:
        model = ConditionReport
        fields = ("piece", "grade", "summary")

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        piece = cleaned.get("piece")
        try:
            flaws = parse_flaws(cleaned.get("flaw_lines", ""))
            cleaned["flaws"] = checked_flaws(piece, flaws) if piece else []
        except ValidationError as error:
            self.add_error("flaw_lines", error)
        return cleaned


@admin.register(ConditionReport)
class ConditionReportAdmin(ModelAdmin):  # type: ignore[type-arg]
    form = ConditionReportForm
    list_display = ("piece", "grade", "flaw_count", "graded_by", "created_at")
    list_filter = ("grade",)
    search_fields = ("piece__title",)
    list_select_related = ("piece", "graded_by")
    autocomplete_fields = ("piece",)
    readonly_fields = ("flaws", "graded_by", "created_at")

    @admin.display(description="Flaws")
    def flaw_count(self, report: ConditionReport) -> int:
        return len(report.flaws)

    def get_fields(self, request: HttpRequest, obj: Any = None) -> Any:
        if obj is None:
            return ("piece", "grade", "summary", "flaw_lines")
        return ("piece", "grade", "summary", "flaws", "graded_by", "created_at")

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False if obj is not None else super().has_change_permission(request, obj)

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def save_model(self, request: HttpRequest, obj: Any, form: Any, change: bool) -> None:
        report = services.add_condition_report(
            form.cleaned_data["piece"],
            grade=form.cleaned_data["grade"],
            summary=form.cleaned_data.get("summary", ""),
            flaws=form.cleaned_data["flaws"],
            by=_staff(request),
        )
        obj.pk = report.pk  # so the admin's "added" message links to the saved report


@admin.register(Restoration)
class RestorationAdmin(DollarsAdmin, ModelAdmin):  # type: ignore[type-arg]
    dollar_fields = (("cost_minor", "What it cost"),)
    list_display = ("piece", "description", "performed_by", "performed_on", "cost")
    search_fields = ("piece__title", "description")
    list_select_related = ("piece",)
    autocomplete_fields = ("piece",)
    fields = ("piece", "description", "performed_by", "performed_on", "cost_minor")
    cost = dollars_column("cost_minor", "What it cost")

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def save_model(self, request: HttpRequest, obj: Any, form: Any, change: bool) -> None:
        services.save_restoration(obj, by=_staff(request))
