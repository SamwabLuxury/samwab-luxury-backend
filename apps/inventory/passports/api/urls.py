from django.urls import path

from apps.inventory.passports.api.views import PassportView

app_name = "passports"

urlpatterns = [
    path("passports/<str:public_code>/", PassportView.as_view(), name="passport"),
]
