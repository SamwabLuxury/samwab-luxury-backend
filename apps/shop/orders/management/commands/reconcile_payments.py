"""Ask the payment provider about every order still waiting for payment.

A safety net for missed webhooks: anything already paid at Stripe is marked paid.
"""

from typing import Any

from django.core.management.base import BaseCommand

from apps.shop.orders import services


class Command(BaseCommand):
    help = "Check waiting orders' payments with the provider (catches missed webhooks)."

    def handle(self, *args: Any, **options: Any) -> None:
        count = services.reconcile_pending()
        self.stdout.write(f"Checked {count} waiting payment(s).")
