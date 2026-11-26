"""The admin site's look (django-unfold), with Django's types (build E16).

Every admin file imports its base classes from here, not from ``unfold`` directly.
At run time they are unfold's classes, which draw the new look. unfold ships no type
hints, so the type checker is shown Django's own classes, which unfold's extend: the
admin files stay fully type-checked and nothing else changes.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.contrib.admin import ModelAdmin, StackedInline, TabularInline
    from django.contrib.admin.widgets import AdminTextInputWidget as TextInput
    from django.contrib.auth.forms import (
        AdminPasswordChangeForm,
        UserChangeForm,
    )
    from django.contrib.auth.forms import (
        AdminUserCreationForm as UserCreationForm,
    )
else:
    from unfold.admin import ModelAdmin as _UnfoldModelAdmin
    from unfold.admin import StackedInline, TabularInline
    from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm
    from unfold.widgets import UnfoldAdminTextInputWidget as TextInput

    class ModelAdmin(_UnfoldModelAdmin):
        """unfold's ModelAdmin, with a list page titled by its plain name.

        Django titles a list "Select piece for sale to change"; staff see
        "Pieces for sale".
        """

        def changelist_view(self, request, extra_context=None):
            title = str(self.model._meta.verbose_name_plural)
            extra = {"title": title[:1].upper() + title[1:], **(extra_context or {})}
            return super().changelist_view(request, extra_context=extra)


__all__ = [
    "AdminPasswordChangeForm",
    "ModelAdmin",
    "StackedInline",
    "TabularInline",
    "TextInput",
    "UserChangeForm",
    "UserCreationForm",
]
