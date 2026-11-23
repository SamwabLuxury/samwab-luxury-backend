"""Stripe events, read only, for superusers checking what Stripe sent."""

from typing import Any

from django.contrib import admin
from django.http import HttpRequest

from apps.payments.models import StripeEvent


@admin.register(StripeEvent)
class StripeEventAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("id", "type", "livemode", "received_at", "processed_at")
    list_filter = ("type", "livemode")
    search_fields = ("id",)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False
