"""Webhooks from payment providers. No login and no CSRF token: the signature
on the raw body is the proof that the request comes from Stripe."""

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.money.payments import services
from apps.money.payments.providers import get_provider


class StripeWebhookView(APIView):
    authentication_classes = ()  # no session, so no CSRF check
    permission_classes = (AllowAny,)

    @extend_schema(
        summary="Stripe webhook",
        description="Checked with the Stripe-Signature header against the raw body, stored once "
        "by event id, then acted on: for payment events the payment's current state is read "
        "from Stripe. 200 when done; 500 if acting on it failed (Stripe retries). A failed "
        "check is 400 `webhook_signature_invalid`.",
        operation_id="webhook_stripe",
        tags=["Webhooks"],
        auth=[],
        request={"application/json": {"type": "object"}},
        responses={200: OpenApiResponse(description="Received")},
    )
    def post(self, request: Request) -> Response:
        # The raw bytes, before anything parses them: the signature covers them exactly.
        body = request._request.body
        event = get_provider().read_webhook(body, request.headers.get("Stripe-Signature"))
        stored, _ = services.record_stripe_event(event)
        services.handle_stripe_event(stored)
        return Response({"received": True})
