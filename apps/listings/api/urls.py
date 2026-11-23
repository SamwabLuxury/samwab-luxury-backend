from django.urls import path

from apps.listings.api.views import ListingDetailView, ListingListView

app_name = "listings"

urlpatterns = [
    path("listings/", ListingListView.as_view(), name="list"),
    path("listings/<uuid:id>/", ListingDetailView.as_view(), name="detail"),
]
