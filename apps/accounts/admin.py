from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import AdminUserCreationForm, UserChangeForm

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
    """Django's user admin, adjusted for login by email."""

    add_form = UserAddForm
    form = UserEditForm

    ordering = ("-id",)
    list_display = ("email", "first_name", "last_name", "country", "is_staff", "is_active")
    list_filter = ("is_staff", "is_superuser", "is_active", "is_house_account")
    search_fields = ("email", "first_name", "last_name")
    readonly_fields = ("id", "last_login", "created_at", "updated_at")

    fieldsets = (
        (None, {"fields": ("id", "email", "password")}),
        (
            "Personal details",
            {"fields": ("first_name", "last_name", "country", "locale", "timezone")},
        ),
        (
            "Account",
            {"fields": ("is_active", "is_house_account", "verification_tier", "anonymised_at")},
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
