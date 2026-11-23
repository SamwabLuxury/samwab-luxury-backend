"""Delete idempotency keys older than their 24-hour lifetime.

Run it once a day. From build 09 the scheduler runs it; until then by hand:
``python manage.py delete_expired_idempotency_keys``.
"""

from typing import Any

from django.core.management.base import BaseCommand

from apps.platform.idempotency import services


class Command(BaseCommand):
    help = "Delete idempotency keys older than their 24-hour lifetime."

    def handle(self, *args: Any, **options: Any) -> None:
        deleted = services.delete_expired()
        self.stdout.write(f"Deleted {deleted} expired idempotency key(s).")
