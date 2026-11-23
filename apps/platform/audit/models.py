"""The audit log table, ``audit_events``, as in the data model.

Rows are only ever added. Django refuses to change or delete one, and on
PostgreSQL a database trigger refuses it too (migration 0002), so not even a
hand-written SQL statement can rewrite history.
"""

from typing import Any, NoReturn

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.utils import timezone

from apps.platform.core.ids import new_uuid


class AuditEventIsFinalError(Exception):
    """Raised on any attempt to change or delete an audit event. A bug, never a user error."""

    def __init__(self) -> None:
        super().__init__("Audit events are append-only: they are never changed or deleted.")


class AuditEventQuerySet(models.QuerySet["AuditEvent"]):
    def update(self, **kwargs: Any) -> NoReturn:
        raise AuditEventIsFinalError()

    def delete(self) -> NoReturn:
        raise AuditEventIsFinalError()


class AuditEvent(models.Model):
    """Who did what to which row, when, and from where.

    - ``action``: ``<app>.<model>.<verb>``, for example ``catalog.brand.retired``.
    - ``object_type`` and ``object_id``: the row it happened to (``catalog.brand`` and its id).
    - ``changes``: ``{"field": {"from": old, "to": new}}``; a new row has only ``to``,
      a deleted row only ``from``. Some actions add their own facts.
    - ``ip_address`` and ``request_id``: from the request, when there was one.
    """

    id = models.UUIDField(primary_key=True, default=new_uuid, editable=False)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,  # people are anonymised, never deleted
        related_name="+",
        help_text="Empty when the system itself made the change.",
    )
    action = models.CharField(max_length=80)
    object_type = models.CharField(max_length=60)
    object_id = models.UUIDField(null=True, blank=True)
    changes = models.JSONField(default=dict, encoder=DjangoJSONEncoder)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    request_id = models.CharField(max_length=64, null=True, blank=True)  # noqa: DJ001
    occurred_at = models.DateTimeField(default=timezone.now)

    objects = AuditEventQuerySet.as_manager()

    class Meta:
        db_table = "audit_events"
        ordering = ("-id",)
        indexes = (
            # "Everything that happened to this piece": the admin's main question.
            models.Index(fields=("object_type", "object_id"), name="audit_events_object_idx"),
        )

    def __str__(self) -> str:
        return f"{self.action} {self.object_id or ''}".strip()

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise AuditEventIsFinalError()
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise AuditEventIsFinalError()
