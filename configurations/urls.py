"""Main URL list. Each app keeps its own URLs and is mounted here."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("apps.core.api.urls")),
    path("api/v1/", include("apps.accounts.api.urls")),
    path("api/v1/", include("apps.catalog.api.urls")),
    # Sign-up, login, email codes and password reset (django-allauth, headless).
    path("_allauth/", include("allauth.headless.urls")),
]

# Used when DEBUG is off: API paths answer in JSON, everything else as a normal page.
handler404 = "apps.core.api.errors.page_not_found"
handler500 = "apps.core.api.errors.server_error"
