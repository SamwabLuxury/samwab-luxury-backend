"""Legal texts in the admin site.

Staff type the owners' wording into a draft, then press "Publish". A published text
is read-only for good; to change it, make a new draft version and publish that.
Acceptances and consents are evidence, so their screens only show them.
"""

from collections.abc import Callable
from typing import Any

from django.contrib import admin, messages
from django.contrib.admin import ActionLocation
from django.db.models import QuerySet
from django.http import HttpRequest

from apps.platform.core.admin_look import ModelAdmin
from apps.platform.core.exceptions import AppError
from apps.users.accounts.models import User
from apps.users.legal import services
from apps.users.legal.models import Consent, LegalDocument, TermsAcceptance


def _staff(request: HttpRequest) -> User:
    user: User = request.user  # type: ignore[assignment]
    return user


@admin.register(LegalDocument)
class LegalDocumentAdmin(ModelAdmin):  # type: ignore[type-arg]
    list_display = ("title", "version", "state", "effective_at", "retired_at")
    list_filter = ("kind",)
    fields = ("kind", "version", "body", "body_sha256", "effective_at", "retired_at")
    readonly_fields = ("body_sha256", "effective_at", "retired_at")
    actions = ("publish_selected", "retire_selected", "new_draft_selected")

    @admin.display(description="State")
    def state(self, document: LegalDocument) -> str:
        if document.is_draft:
            return "Draft"
        return "In force" if document.is_in_force else "Retired"

    def get_readonly_fields(self, request: HttpRequest, obj: Any = None) -> Any:
        if obj is None:
            return self.readonly_fields
        return ("kind", *self.readonly_fields)  # a version stays with its kind

    def get_actions(
        self, request: HttpRequest, action_location: Any = ActionLocation.CHANGE_LIST
    ) -> Any:
        actions = super().get_actions(request, action_location=action_location)
        actions.pop("delete_selected", None)  # drafts are deleted one at a time
        return actions

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        if obj is not None and not obj.is_draft:
            return False  # published words never change
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        if obj is not None and not obj.is_draft:
            return False
        return super().has_delete_permission(request, obj)

    def save_model(self, request: HttpRequest, obj: Any, form: Any, change: bool) -> None:
        services.save_draft(obj, by=_staff(request))

    def delete_model(self, request: HttpRequest, obj: Any) -> None:
        services.delete_draft(obj, by=_staff(request))

    def _each(
        self,
        request: HttpRequest,
        queryset: QuerySet[LegalDocument],
        step: Callable[..., LegalDocument],
        done: str,
    ) -> None:
        for document in queryset:
            try:
                result = step(document, by=_staff(request))
            except AppError as error:
                self.message_user(request, f"{document}: {error.message}", messages.ERROR)
            else:
                self.message_user(request, done.format(result=result))

    @admin.action(description="Publish the selected drafts now", permissions=["change"])
    def publish_selected(self, request: HttpRequest, queryset: QuerySet[LegalDocument]) -> None:
        self._each(
            request,
            queryset,
            services.publish,
            "Published {result.title}, version {result.version}. It is in force now.",
        )

    @admin.action(description="Retire the selected texts", permissions=["change"])
    def retire_selected(self, request: HttpRequest, queryset: QuerySet[LegalDocument]) -> None:
        self._each(request, queryset, services.retire, "Retired {result}.")

    @admin.action(description="Make a new draft version of the selected texts", permissions=["add"])
    def new_draft_selected(self, request: HttpRequest, queryset: QuerySet[LegalDocument]) -> None:
        def start(document: LegalDocument, *, by: User) -> LegalDocument:
            return services.new_draft(document.kind, by=by)

        self._each(request, queryset, start, "Made {result}.")


class EvidenceAdmin(ModelAdmin):  # type: ignore[type-arg]
    """Read-only: these rows are the record of what people agreed to."""

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


@admin.register(TermsAcceptance)
class TermsAcceptanceAdmin(EvidenceAdmin):
    list_display = ("user", "legal_document", "accepted_at", "ip_address", "signed_name")
    list_filter = ("legal_document__kind",)
    list_select_related = ("user", "legal_document")
    search_fields = ("user__email",)
    fields = (
        "user",
        "legal_document",
        "order",
        "accepted_at",
        "ip_address",
        "user_agent",
        "signed_name",
    )


@admin.register(Consent)
class ConsentAdmin(EvidenceAdmin):
    list_display = ("user", "kind", "granted_at", "withdrawn_at", "legal_document")
    list_filter = ("kind",)
    list_select_related = ("user", "legal_document")
    search_fields = ("user__email",)
    fields = ("user", "kind", "legal_document", "granted_at", "withdrawn_at")
