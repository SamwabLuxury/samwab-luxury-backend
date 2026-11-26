"""Send any order confirmation emails a mail outage held back (build E21).

Safe to run any time, as often as you like: each paid order gets its email once.
On Render: Shell tab, then ``python manage.py send_order_confirmations``.
"""

from typing import Any

from django.core.management.base import BaseCommand

from apps.shop.orders import emails


class Command(BaseCommand):
    help = "Send order confirmation emails that have not gone out yet."

    def handle(self, *args: Any, **options: Any) -> None:
        waiting = list(emails.unsent_confirmations().values_list("pk", flat=True))
        sent = sum(emails.send_confirmation(pk) for pk in waiting)
        self.stdout.write(f"Sent {sent} of {len(waiting)} waiting confirmation(s).")
