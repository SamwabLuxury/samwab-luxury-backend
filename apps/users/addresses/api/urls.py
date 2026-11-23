from django.urls import path

from apps.users.addresses.api.views import AddressListView

app_name = "addresses"

urlpatterns = [
    path("me/addresses/", AddressListView.as_view(), name="list"),
]
