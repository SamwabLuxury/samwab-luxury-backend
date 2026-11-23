"""The audit log screen: read only, for everyone, superusers included."""

import json
from typing import Any

from django.contrib import admin
from django.contrib.admin import ActionLocation
from django.http import HttpRequest
from django.utils.html import format_html

from apps.platform.audit.models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("occurred_at", "actor", "action", "object_type", "object_id", "ip_address")
    list_filter = ("object_type", "action")
    list_select_related = ("actor",)
    search_fields = ("=object_id", "=request_id", "actor__email", "action")
    date_hierarchy = "occurred_at"
    fields = (
        "occurred_at",
        "actor",
        "action",
        "object_type",
        "object_id",
        "changes_shown",
        "ip_address",
        "request_id",
    )
    readonly_fields = fields

    @admin.display(description="changes")
    def changes_shown(self, event: AuditEvent) -> str:
        return format_html("<pre>{}</pre>", json.dumps(event.changes, indent=2, ensure_ascii=False))

    def get_actions(
        self, request: HttpRequest, action_location: Any = ActionLocation.CHANGE_LIST
    ) -> Any:
        actions = super().get_actions(request, action_location=action_location)
        actions.pop("delete_selected", None)
        return actions

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False
