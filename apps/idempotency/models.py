"""The ``idempotency_keys`` table, as in the data model.

One row per key a person has sent. While the first request runs,
``response_status`` is empty; when it finishes, the answer is kept so a retry
gets the same answer without the work running again.
"""

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.utils import timezone

from apps.core.ids import new_uuid


class IdempotencyKey(models.Model):
    id = models.UUIDField(primary_key=True, default=new_uuid, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,  # keys live 24 hours; they never hold anyone back
        related_name="+",
    )
    key = models.CharField(max_length=255)
    endpoint = models.CharField(
        max_length=120, help_text="Method and path, such as POST /api/v1/orders/"
    )
    request_sha256 = models.CharField(max_length=64, help_text="Fingerprint of the request body")
    response_status = models.PositiveSmallIntegerField(null=True, blank=True)
    response_body = models.JSONField(null=True, blank=True, encoder=DjangoJSONEncoder)
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = "idempotency_keys"
        constraints = (
            models.UniqueConstraint(fields=("user", "key"), name="idempotency_keys_user_key_uniq"),
        )
        indexes = (models.Index(fields=("expires_at",), name="idempotency_keys_expires_idx"),)

    def __str__(self) -> str:
        return f"{self.endpoint} {self.key}"

    @property
    def is_finished(self) -> bool:
        return self.response_status is not None
