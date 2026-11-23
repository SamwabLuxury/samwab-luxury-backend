from django.urls import path

from apps.money.payments.api.views import StripeWebhookView

app_name = "payments"

urlpatterns = [
    path("webhooks/stripe/", StripeWebhookView.as_view(), name="stripe-webhook"),
]
