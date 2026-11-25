from django.urls import path

from apps.shop.listings.api.saved_views import SavedListingView, SavedListView
from apps.shop.listings.api.views import ListingDetailView, ListingListView

app_name = "listings"

urlpatterns = [
    path("listings/", ListingListView.as_view(), name="list"),
    path("listings/<uuid:id>/", ListingDetailView.as_view(), name="detail"),
    path("me/saved/", SavedListView.as_view(), name="saved-list"),
    path("me/saved/<uuid:listing_id>/", SavedListingView.as_view(), name="saved"),
]
