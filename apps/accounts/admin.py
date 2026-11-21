from typing import Any

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import AdminUserCreationForm, UserChangeForm
from django.http import HttpRequest

from apps.accounts import services
from apps.accounts.models import User


class UserAddForm(AdminUserCreationForm):  # type: ignore[type-arg]
    class Meta:
        model = User
        fields = ("email",)


class UserEditForm(UserChangeForm):  # type: ignore[type-arg]
    class Meta:
        model = User
        fields = "__all__"


@admin.register(User)
class UserAdmin(DjangoUserAdmin):  # type: ignore[type-arg]
    """Django's user admin, adjusted for login by email.

    Every add or change is audited, roles (groups) included. Roles are saved after
    the account itself (in ``save_related``), so the event is written there.
    """

    add_form = UserAddForm
    form = UserEditForm

    ordering = ("-id",)
    list_display = ("email", "first_name", "last_name", "country", "is_staff", "is_active")
    list_filter = ("signup_intent", "is_staff", "is_superuser", "is_active", "is_house_account")
    search_fields = ("email", "first_name", "last_name")
    readonly_fields = ("id", "signup_intent", "last_login", "created_at", "updated_at")

    fieldsets = (
        (None, {"fields": ("id", "email", "password")}),
        (
            "Personal details",
            {"fields": ("first_name", "last_name", "country", "locale", "timezone")},
        ),
        (
            "Account",
            {
                "fields": (
                    "is_active",
                    "signup_intent",
                    "is_house_account",
                    "verification_tier",
                    "anonymised_at",
                )
            },
        ),
        (
            "Staff access",
            {"fields": ("is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("Dates", {"fields": ("last_login", "created_at", "updated_at")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "usable_password", "password1", "password2"),
            },
        ),
    )

    def save_model(self, request: HttpRequest, obj: Any, form: Any, change: bool) -> None:
        stored = User.objects.get(pk=obj.pk) if change else None
        obj._audit_before = None if stored is None else services.staff_view_of(stored)
        super().save_model(request, obj, form, change)

    def save_related(self, request: HttpRequest, form: Any, formsets: Any, change: bool) -> None:
        super().save_related(request, form, formsets, change)
        staff: User = request.user  # type: ignore[assignment]
        services.record_staff_edit(form.instance, before=form.instance._audit_before, by=staff)
