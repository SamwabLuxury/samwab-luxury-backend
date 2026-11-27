"""Legal texts, who accepted which version, and consents (build 11).

Tables as in the data model, with one change: the exact text is kept in ``body`` in
the database (the data model names a file storage key). It is just as write-once: a
text can change only while it is a draft, and its SHA-256 is saved when it is written.

A text's state comes from its two dates, never from a separate status column:

- draft: no ``effective_at`` yet. Staff may edit it; nobody can accept it.
- in force: ``effective_at`` set, ``retired_at`` empty. At most one per kind.
- retired: ``retired_at`` set. Acceptances of it stay, as history.
"""

from typing import Any, NoReturn

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from apps.platform.core.ids import new_uuid
from apps.platform.core.models import BaseModel
from apps.users.legal.enums import ConsentKind, DocumentKind


class LegalDocument(BaseModel):
    kind = models.CharField(max_length=30, choices=DocumentKind.choices)
    version = models.CharField(
        max_length=20, help_text="For example 1, 2 or 2026-11. Unique for each kind of text."
    )
    body = models.TextField(
        "text",
        help_text="The exact words shown to people. Paragraphs are separated by a blank line.",
    )
    body_sha256 = models.CharField(max_length=64, editable=False)
    effective_at = models.DateTimeField(
        "in force since", null=True, blank=True, editable=False, help_text="Empty for a draft."
    )
    retired_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        db_table = "legal_documents"
        ordering = ("kind", "-created_at")
        verbose_name = "legal text"
        constraints = (
            models.UniqueConstraint(
                fields=("kind", "version"), name="legal_documents_kind_version"
            ),
            models.UniqueConstraint(
                fields=("kind",),
                condition=Q(effective_at__isnull=False, retired_at__isnull=True),
                name="legal_documents_one_in_force_per_kind",
            ),
            models.UniqueConstraint(
                fields=("kind",),
                condition=Q(effective_at__isnull=True),
                name="legal_documents_one_draft_per_kind",
            ),
            models.CheckConstraint(
                condition=Q(kind__in=DocumentKind.values), name="legal_documents_kind_is_known"
            ),
            models.CheckConstraint(
                condition=Q(retired_at__isnull=True)
                | Q(effective_at__isnull=False, retired_at__gte=F("effective_at")),
                name="legal_documents_retired_after_in_force",
            ),
        )

    def __str__(self) -> str:
        state = "draft" if self.is_draft else "in force" if self.is_in_force else "retired"
        return f"{self.title}, version {self.version} ({state})"

    @property
    def title(self) -> str:
        return str(DocumentKind(self.kind).label)

    @property
    def is_draft(self) -> bool:
        return self.effective_at is None

    @property
    def is_in_force(self) -> bool:
        return self.effective_at is not None and self.retired_at is None


class TermsAcceptanceIsFinalError(Exception):
    """Raised on any attempt to change or delete an acceptance. A bug, never a user error."""

    def __init__(self) -> None:
        super().__init__("Acceptances are append-only: they are never changed or deleted.")


class TermsAcceptanceQuerySet(models.QuerySet["TermsAcceptance"]):
    def update(self, **kwargs: Any) -> NoReturn:
        raise TermsAcceptanceIsFinalError()

    def delete(self) -> NoReturn:
        raise TermsAcceptanceIsFinalError()


class TermsAcceptance(models.Model):
    """One person accepted one version of a text, at a time, from an IP address.

    Append-only, like the audit log: Django refuses to change or delete a row, and on
    PostgreSQL a trigger refuses it too (migration 0002).
    """

    id = models.UUIDField(primary_key=True, default=new_uuid, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="terms_acceptances"
    )
    legal_document = models.ForeignKey(
        LegalDocument, on_delete=models.PROTECT, related_name="acceptances"
    )
    order = models.ForeignKey(
        "orders.Order",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="Only for forms signed per order, such as the buyer authentication form.",
    )
    accepted_at = models.DateTimeField(default=timezone.now)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True, help_text="The browser she used.")
    signed_name = models.CharField(
        max_length=160, blank=True, help_text="Her typed full name, for texts she signs."
    )

    objects = TermsAcceptanceQuerySet.as_manager()

    class Meta:
        db_table = "terms_acceptances"
        ordering = ("-accepted_at", "-id")
        verbose_name = "terms accepted"
        verbose_name_plural = "terms accepted"
        constraints = (
            # The data model asks for one unique index with NULLS NOT DISTINCT. Django
            # applies that option on PostgreSQL only, so two partial indexes do the same
            # job on both databases (as for capture protocols, D31).
            models.UniqueConstraint(
                fields=("user", "legal_document"),
                condition=Q(order__isnull=True),
                name="terms_acceptances_once_per_account",
            ),
            models.UniqueConstraint(
                fields=("user", "legal_document", "order"),
                condition=Q(order__isnull=False),
                name="terms_acceptances_once_per_order",
            ),
        )

    def __str__(self) -> str:
        return f"{self.legal_document} accepted"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise TermsAcceptanceIsFinalError()
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise TermsAcceptanceIsFinalError()


class Consent(models.Model):
    """Something she agreed to, under the privacy policy in force at the time.

    Withdrawing fills ``withdrawn_at``; agreeing again adds a new row, so the history
    of every yes and no stays.
    """

    id = models.UUIDField(primary_key=True, default=new_uuid, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="consents"
    )
    kind = models.CharField(max_length=30, choices=ConsentKind.choices)
    legal_document = models.ForeignKey(
        LegalDocument,
        on_delete=models.PROTECT,
        related_name="consents",
        help_text="The privacy policy in force when she agreed.",
    )
    granted_at = models.DateTimeField(default=timezone.now)
    withdrawn_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "consents"
        ordering = ("-granted_at", "-id")
        constraints = (
            models.UniqueConstraint(
                fields=("user", "kind"),
                condition=Q(withdrawn_at__isnull=True),
                name="consents_one_active_per_kind",
            ),
            models.CheckConstraint(
                condition=Q(kind__in=ConsentKind.values), name="consents_kind_is_known"
            ),
            models.CheckConstraint(
                condition=Q(withdrawn_at__isnull=True) | Q(withdrawn_at__gte=F("granted_at")),
                name="consents_withdrawn_after_granted",
            ),
        )

    def __str__(self) -> str:
        return f"{ConsentKind(self.kind).label} ({'withdrawn' if self.withdrawn_at else 'given'})"
