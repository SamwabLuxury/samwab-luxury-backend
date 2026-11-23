"""Idempotency keys, read only, for looking into a support question."""

from typing import Any

from django.contrib import admin
from django.http import HttpRequest

from apps.platform.idempotency.models import IdempotencyKey


@admin.register(IdempotencyKey)
class IdempotencyKeyAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("created_at", "user", "endpoint", "key", "response_status", "expires_at")
    list_select_related = ("user",)
    search_fields = ("=key", "user__email", "endpoint")
    readonly_fields = (
        "user",
        "key",
        "endpoint",
        "request_sha256",
        "response_status",
        "response_body",
        "created_at",
        "expires_at",
    )
    fields = readonly_fields

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False
