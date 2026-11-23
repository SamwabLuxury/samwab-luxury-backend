"""Stripe webhook events, stored once each, exactly as Stripe sent them.

The table follows the data model (``stripe_events``): the primary key is Stripe's
own event id (``evt_...``), so a repeated delivery cannot be stored twice.
Processing (``processed_at``, ``attempts``, ``last_error``) starts with orders.
"""

from django.db import models
from django.utils import timezone


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
