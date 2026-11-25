"""Listing house stock in the admin site.

Draft a listing for a piece, then publish it with the action on the list page.
Its asking price can change while it is open; every change is kept in its price
history. Withdraw it to take it off sale. Listings are never deleted.

Every save and action goes through ``services``, which check the rules and
record audit events. The price explainer's adjustments ("Complete set, +$300") are
edited in their own table on the listing's page; each row saved is audited too.
"""

from typing import Any

from django import forms
from django.contrib import admin, messages
from django.contrib.admin import ActionLocation
from django.db.models import QuerySet
from django.http import HttpRequest

from apps.platform.audit import services as audit
from apps.platform.core.exceptions import AppError
from apps.shop.listings import services
from apps.shop.listings.enums import OPEN_STATUSES
from apps.shop.listings.models import Listing, ListingPriceAdjustment, ListingPriceChange
from apps.users.accounts.models import User


def _staff(request: HttpRequest) -> User:
    return request.user  # type: ignore[return-value]


class ListingForm(forms.ModelForm):  # type: ignore[type-arg]
    class Meta:
        model = Listing
        fields = ("piece", "fulfilment", "ask_minor")

    def clean(self) -> dict[str, Any]:
        data: dict[str, Any] = super().clean() or {}
        piece = data.get("piece")
        if (
            self.instance._state.adding
            and piece is not None
            and Listing.objects.filter(piece=piece, status__in=OPEN_STATUSES).exists()
        ):
            self.add_error("piece", "This piece already has an open listing. Withdraw it first.")
        return data


class PriceChangeInline(admin.TabularInline):  # type: ignore[type-arg]
    model = ListingPriceChange
    fields = ("changed_at", "change", "changed_by")
    readonly_fields = fields
    extra = 0
    can_delete = False
    verbose_name_plural = "price history"

    @admin.display(description="price")
    def change(self, row: ListingPriceChange) -> str:
        return str(row)

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


class PriceAdjustmentInline(admin.TabularInline):  # type: ignore[type-arg]
    """The staff's lines of the price explainer, shown on the piece page in this order."""

    model = ListingPriceAdjustment
    fields = ("sort_order", "label", "direction", "amount_minor")
    extra = 0
    verbose_name_plural = "price explainer: adjustments"


@admin.register(Listing)
class ListingAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    form = ListingForm
    list_display = ("piece", "price", "fulfilment", "status", "published_at")
    list_filter = ("status", "fulfilment")
    list_select_related = ("piece",)
    search_fields = ("piece__title", "piece__brand__name", "piece__product_model__name")
    autocomplete_fields = ("piece",)
    inlines = (PriceChangeInline, PriceAdjustmentInline)
    actions = ("publish_selected", "withdraw_selected")

    @admin.display(description="asking price", ordering="ask_minor")
    def price(self, listing: Listing) -> str:
        return str(listing.ask)

    def get_fields(self, request: HttpRequest, obj: Any = None) -> Any:
        if obj is None:
            return ("piece", "fulfilment", "ask_minor")
        return ("piece", "seller", "status", "published_at", "fulfilment", "ask_minor")

    def get_readonly_fields(self, request: HttpRequest, obj: Any = None) -> Any:
        if obj is None:
            return ()
        # Change the piece or fulfilment by withdrawing and drafting a new listing.
        return ("piece", "seller", "status", "published_at", "fulfilment")

    def get_actions(
        self, request: HttpRequest, action_location: Any = ActionLocation.CHANGE_LIST
    ) -> Any:
        actions = super().get_actions(request, action_location=action_location)
        actions.pop("delete_selected", None)  # listings are never deleted
        return actions

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        if obj is not None and not obj.is_open:
            return False  # a closed listing is kept as it was
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def save_model(self, request: HttpRequest, obj: Any, form: Any, change: bool) -> None:
        if change:
            services.change_ask(obj, ask_minor=form.cleaned_data["ask_minor"], by=_staff(request))
        else:
            services.create_listing(obj, by=_staff(request))

    def save_formset(self, request: HttpRequest, form: Any, formset: Any, change: bool) -> None:
        audit.save_inline_rows(formset, by=_staff(request))

    def _each(
        self, request: HttpRequest, queryset: QuerySet[Listing], step: Any, done: str
    ) -> None:
        for listing in queryset.select_related("piece"):
            try:
                step(listing, by=_staff(request))
            except AppError as error:
                self.message_user(request, f"{listing.piece}: {error.message}", messages.ERROR)
            else:
                self.message_user(request, f"{done} {listing.piece}.")

    @admin.action(description="Publish the selected drafts")
    def publish_selected(self, request: HttpRequest, queryset: QuerySet[Listing]) -> None:
        self._each(request, queryset, services.publish_listing, "Published")

    @admin.action(description="Withdraw the selected listings")
    def withdraw_selected(self, request: HttpRequest, queryset: QuerySet[Listing]) -> None:
        self._each(request, queryset, services.withdraw_listing, "Withdrew")
