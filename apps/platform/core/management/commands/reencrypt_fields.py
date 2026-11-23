"""Re-encrypt every encrypted column with the first key in DJANGO_FIELD_ENCRYPTION_KEYS.

Run it after putting a new key first, then remove the old key. Safe to run twice.
"""

from typing import Any

from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.platform.core.fields import EncryptedTextField


class Command(BaseCommand):
    help = "Re-encrypt every encrypted column with the first key (run after adding a new key)."

    def handle(self, *args: Any, **options: Any) -> None:
        for model in apps.get_models():
            fields = [
                f.name for f in model._meta.concrete_fields if isinstance(f, EncryptedTextField)
            ]
            if not fields:
                continue
            count = 0
            # Reading decrypts with any key; saving encrypts with the first.
            for row in model._default_manager.iterator(chunk_size=500):
                with transaction.atomic():
                    row.save(update_fields=fields)
                count += 1
            self.stdout.write(f"{model._meta.label}: {count} rows re-encrypted.")
