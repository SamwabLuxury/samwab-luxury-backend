"""The admin's second-step pages, mounted at /admin/two-step/ before the admin itself."""

from django.urls import path

from apps.users.accounts import two_step_views

app_name = "two_step"

urlpatterns = [
    path("", two_step_views.verify, name="verify"),
    path("setup/", two_step_views.setup, name="setup"),
]
