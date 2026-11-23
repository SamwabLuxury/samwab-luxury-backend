from django.urls import path

from apps.users.accounts.api.views import MeView

app_name = "accounts"

urlpatterns = [
    path("me/", MeView.as_view(), name="me"),
]
