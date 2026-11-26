"""The mailing list in the admin site: read-only. People join and leave by email only,
so their consent is always their own."""

from typing import Any

from django.contrib import admin
from django.http import HttpRequest

from apps.platform.core.admin_look import ModelAdmin
from apps.users.mailing_list.models import ListMember


@admin.register(ListMember)
class ListMemberAdmin(ModelAdmin):  # type: ignore[type-arg]
    list_display = ("email", "status", "source", "confirmed_at", "unsubscribed_at", "created_at")
    list_filter = ("status", "source")
    search_fields = ("email",)
    readonly_fields = (
        "email",
        "status",
        "source",
        "confirm_sent_at",
        "confirmed_at",
        "unsubscribed_at",
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False
