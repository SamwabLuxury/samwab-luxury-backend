from django.urls import path

from apps.users.mailing_list.api.views import ConfirmView, JoinView, UnsubscribeView

app_name = "mailing_list"

urlpatterns = [
    path("mailing-list/", JoinView.as_view(), name="join"),
    path("mailing-list/confirm/", ConfirmView.as_view(), name="confirm"),
    path("mailing-list/unsubscribe/", UnsubscribeView.as_view(), name="unsubscribe"),
]
