"""Stripe webhook events, stored once each, exactly as Stripe sent them.

The table follows the data model (``stripe_events``): the primary key is Stripe's
own event id (``evt_...``), so a repeated delivery cannot be stored twice.
Each payment event is acted on once (``processed_at``); a failure is kept in
``last_error`` and Stripe's retry tries again.

``payments`` and ``refunds`` follow the data model too; their Stripe id columns
keep the data model's names, while the code calls them provider ids.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import BaseModel


class StripeEvent(models.Model):
    id = models.CharField(primary_key=True, max_length=255, help_text="Stripe's event id, evt_...")
    type = models.CharField(max_length=100)
    livemode = models.BooleanField()
    payload = models.JSONField()
    received_at = models.DateTimeField(default=timezone.now)
    processed_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.TextField(blank=True)

    class Meta:
        db_table = "stripe_events"
        ordering = ("-received_at",)
        indexes = (
            models.Index(fields=("processed_at", "received_at"), name="stripe_events_todo_idx"),
        )

    def __str__(self) -> str:
        return f"{self.id} · {self.type}"


class Payment(BaseModel):
    """One payment at the provider for one order (a PaymentIntent at Stripe).

    The status mirrors the provider's and is only ever copied from what the
    provider says (``services.payment_changed``), never from the browser.
    """

    order = models.ForeignKey("orders.Order", on_delete=models.PROTECT, related_name="payments")
    provider_payment_id = models.CharField(
        max_length=255, unique=True, db_column="stripe_payment_intent_id"
    )
    charge_type = models.CharField(max_length=20, default="direct")
    kind = models.CharField(max_length=20, default="full")
    amount_minor = models.PositiveBigIntegerField()
    currency = models.CharField(max_length=3)
    payment_method_type = models.CharField(max_length=30, blank=True)
    off_session = models.BooleanField(default=False)
    status = models.CharField(max_length=30)
    failure_reason = models.CharField(
        max_length=255, blank=True, help_text="The last attempt's error, for support."
    )
    idempotency_key = models.CharField(max_length=255, unique=True)

    class Meta:
        db_table = "payments"
        ordering = ("-id",)
        constraints = (
            models.CheckConstraint(
                condition=models.Q(kind__in=("full", "reservation_deposit", "remainder")),
                name="payments_kind_is_known",
            ),
        )

    def __str__(self) -> str:
        return f"{self.provider_payment_id} · {self.status}"


class Refund(BaseModel):
    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name="refunds")
    provider_refund_id = models.CharField(max_length=255, unique=True, db_column="stripe_refund_id")
    amount_minor = models.PositiveBigIntegerField()
    currency = models.CharField(max_length=3)
    reason = models.CharField(max_length=30)
    reverse_transfer = models.BooleanField(default=False)
    status = models.CharField(max_length=20)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        db_table = "refunds"
        ordering = ("-id",)

    def __str__(self) -> str:
        return f"{self.provider_refund_id} · {self.reason}"
