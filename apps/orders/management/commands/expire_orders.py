"""Close orders whose 15-minute hold ran out and put their pieces back on sale.

Holds are also released when the next buyer comes; run this on a schedule so
pieces do not look held for long. An order that turns out paid stays paid.
"""

from typing import Any

from django.core.management.base import BaseCommand

from apps.orders import services


class Command(BaseCommand):
    help = "Cancel unpaid orders whose checkout hold ran out."

    def handle(self, *args: Any, **options: Any) -> None:
        count = services.expire_stale_orders()
        self.stdout.write(f"Looked at {count} order(s) past their hold.")
