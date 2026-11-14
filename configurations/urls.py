"""Main URL list. Each app keeps its own URLs and is mounted here."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("apps.core.api.urls")),
]

# Used when DEBUG is off: API paths answer in JSON, everything else as a normal page.
handler404 = "apps.core.api.errors.page_not_found"
handler500 = "apps.core.api.errors.server_error"
