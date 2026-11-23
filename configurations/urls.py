"""Main URL list. Each app keeps its own URLs and is mounted here."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import URLPattern, URLResolver, include, path

urlpatterns: list[URLPattern | URLResolver] = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("apps.platform.core.api.urls")),
    path("api/v1/", include("apps.users.accounts.api.urls")),
    path("api/v1/", include("apps.inventory.catalog.api.urls")),
    path("api/v1/", include("apps.shop.listings.api.urls")),
    path("api/v1/", include("apps.users.addresses.api.urls")),
    path("api/v1/", include("apps.shop.orders.api.urls")),
    path("", include("apps.money.payments.urls")),
    # Sign-up, login, email codes and password reset (django-allauth, headless).
    path("_allauth/", include("allauth.headless.urls")),
]

# On your machine (DEBUG on), Django serves uploaded photos itself. The live site
# serves them from the storage (a cloud bucket), never through Django.
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Used when DEBUG is off: API paths answer in JSON, everything else as a normal page.
handler404 = "apps.platform.core.api.errors.page_not_found"
handler500 = "apps.platform.core.api.errors.server_error"
