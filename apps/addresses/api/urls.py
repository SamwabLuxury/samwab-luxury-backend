from django.urls import path

from apps.addresses.api.views import AddressListView

app_name = "addresses"

urlpatterns = [
    path("me/addresses/", AddressListView.as_view(), name="list"),
]
