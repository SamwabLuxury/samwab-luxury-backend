"""Changes to legal texts, acceptances and consents. Views and the admin call these.

Staff write a draft, then publish it. Publishing puts it in force and retires the
version it replaces; from then on its words never change. People accept only the
version in force, and each acceptance is kept for good with its time and IP address.
"""

import hashlib
from collections.abc import Iterable
from typing import Any
from uuid import UUID

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.platform.audit import services as audit
from apps.platform.core.exceptions import NotFoundError
from apps.users.accounts.models import User
from apps.users.legal import selectors
from apps.users.legal.enums import NEEDS_SIGNATURE, PER_ORDER, DocumentKind
from apps.users.legal.exceptions import (
    DraftAlreadyExistsError,
    LegalDocumentNotCurrentError,
    LegalDocumentNotDraftError,
    LegalDocumentNotInForceError,
    OrderNotNeededError,
    OrderRequiredError,
    PlaceholderTextError,
    PrivacyPolicyNotPublishedError,
    SignedNameRequiredError,
)
from apps.users.legal.models import Consent, LegalDocument, TermsAcceptance

# Wording that marks a text as not real yet. A text containing it cannot be published.
PLACEHOLDER_MARK = "[PLACEHOLDER"

# The body can be long, so the audit log records its SHA-256 instead of the words.
_NOT_AUDITED = ("body",)

# Recorded when the caller's address is not known (outside a web request).
UNKNOWN_ADDRESS = "0.0.0.0"  # noqa: S104 (a value stored, not an address listened on)


def placeholder_text(kind: str) -> str:
    title = DocumentKind(kind).label
    return (
        f"{PLACEHOLDER_MARK}: Samwab's {str(title).lower()} will appear here.]\n\n"
        "Staff replace this text with the wording from the owners or their lawyer, "
        "then publish it."
    )


def tidy(body: str) -> str:
    """The text as kept: Windows line ends made plain, no spaces at line ends or edges."""
    lines = body.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return "\n".join(line.rstrip() for line in lines).strip()


def _fingerprint(document: LegalDocument) -> None:
    document.body = tidy(document.body)
    document.body_sha256 = hashlib.sha256(document.body.encode()).hexdigest()


def _locked(document: LegalDocument) -> LegalDocument:
    return LegalDocument.objects.select_for_update().get(pk=document.pk)


# ---------- staff: drafts and publishing ----------


@transaction.atomic
def save_draft(document: LegalDocument, *, by: User) -> LegalDocument:
    """Add a draft, or save changes to one. A published text is never changed."""
    before = None
    if not document._state.adding:
        if not _locked(document).is_draft:
            raise LegalDocumentNotDraftError()
        before = audit.snapshot(LegalDocument.objects.get(pk=document.pk), exclude=_NOT_AUDITED)
    _fingerprint(document)
    document.full_clean()
    document.save()
    audit.record_saved(document, before=before, by=by, exclude=_NOT_AUDITED)
    return document


def _next_version(kind: str) -> str:
    taken = set(LegalDocument.objects.filter(kind=kind).values_list("version", flat=True))
    numbered = [int(version) for version in taken if version.isdigit()]
    number = max([*numbered, len(taken)]) + 1
    while str(number) in taken:  # pragma: no cover - only if staff typed the next number
        number += 1
    return str(number)


@transaction.atomic
def new_draft(kind: str, *, by: User) -> LegalDocument:
    """Start the next version of ``kind``, from the text in force (or a placeholder)."""
    if LegalDocument.objects.filter(kind=kind, effective_at__isnull=True).exists():
        raise DraftAlreadyExistsError()
    current = selectors.in_force(kind)
    draft = LegalDocument(
        kind=kind,
        version=_next_version(kind),
        body=current.body if current else placeholder_text(kind),
    )
    return save_draft(draft, by=by)


@transaction.atomic
def publish(document: LegalDocument, *, by: User) -> LegalDocument:
    """Put a draft in force now. The version it replaces is retired at the same moment."""
    current = _locked(document)
    if not current.is_draft:
        raise LegalDocumentNotDraftError()
    if PLACEHOLDER_MARK in current.body:
        raise PlaceholderTextError()
    now = timezone.now()
    replaced = (
        LegalDocument.objects.select_for_update()
        .filter(selectors.IN_FORCE, kind=current.kind)
        .first()
    )
    if replaced is not None:
        replaced.retired_at = now
        replaced.save(update_fields=["retired_at", "updated_at"])
        audit.record("retired", replaced, by=by, changes={"replaced_by": current.version})
    current.effective_at = now
    current.save(update_fields=["effective_at", "updated_at"])
    audit.record(
        "published",
        current,
        by=by,
        changes={"version": current.version, "body_sha256": current.body_sha256},
    )
    document.effective_at = current.effective_at
    return current


@transaction.atomic
def retire(document: LegalDocument, *, by: User) -> LegalDocument:
    """Take the version in force out of use, leaving none in force for its kind."""
    current = _locked(document)
    if not current.is_in_force:
        raise LegalDocumentNotInForceError()
    current.retired_at = timezone.now()
    current.save(update_fields=["retired_at", "updated_at"])
    audit.record("retired", current, by=by, changes={"version": current.version})
    return current


@transaction.atomic
def delete_draft(document: LegalDocument, *, by: User) -> None:
    """Delete a draft. Published texts stay for good, as the record of what was agreed."""
    current = _locked(document)
    if not current.is_draft:
        raise LegalDocumentNotDraftError()
    before = audit.snapshot(current, exclude=_NOT_AUDITED)
    document_id = current.pk
    current.delete()
    audit.record_deleted(LegalDocument, document_id, before=before, by=by)


# ---------- people: accepting ----------


def _order_of(user: User, order_id: UUID) -> Any:
    """Her own order, as buyer. The model is looked up through the foreign key, so this
    app does not import the shop (orders already depend on it)."""
    order_model: Any = TermsAcceptance._meta.get_field("order").related_model
    order = order_model.objects.filter(pk=order_id, buyer=user).first()
    if order is None:
        raise NotFoundError()
    return order


def accept(
    user: User,
    *,
    kind: str,
    version: str,
    ip_address: str | None,
    user_agent: str = "",
    signed_name: str = "",
    order_id: UUID | None = None,
) -> TermsAcceptance:
    """Record that she accepted ``version`` of ``kind``. Accepting again returns the first
    record. Only the version in force can be accepted (409 otherwise)."""
    document = selectors.in_force(kind)
    if document is None or document.version != version:
        raise LegalDocumentNotCurrentError()
    signed_name = signed_name.strip()
    if kind in NEEDS_SIGNATURE and not signed_name:
        raise SignedNameRequiredError()
    if kind in PER_ORDER and order_id is None:
        raise OrderRequiredError()
    if kind not in PER_ORDER and order_id is not None:
        raise OrderNotNeededError()
    order = _order_of(user, order_id) if order_id is not None else None

    try:
        with transaction.atomic():  # one row per account and version: the database decides
            return TermsAcceptance.objects.create(
                user=user,
                legal_document=document,
                order=order,
                ip_address=ip_address or UNKNOWN_ADDRESS,
                user_agent=user_agent[:500],
                signed_name=signed_name,
            )
    except IntegrityError:  # accepted before (or from two tabs at once): keep the first
        return TermsAcceptance.objects.get(user=user, legal_document=document, order=order)


def accept_in_force(
    user: User, kinds: Iterable[str], *, ip_address: str | None, user_agent: str = ""
) -> list[TermsAcceptance]:
    """Accept the version in force of each kind (sign-up's "I agree" box). Kinds with
    nothing in force are skipped."""
    return [
        accept(
            user,
            kind=document.kind,
            version=document.version,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        for document in selectors.missing(user, kinds)
    ]


# ---------- people: consents ----------


def grant_consent(user: User, kind: str) -> Consent:
    """Agree to ``kind`` under the privacy policy in force. Agreeing again changes nothing."""
    existing = Consent.objects.filter(user=user, kind=kind, withdrawn_at__isnull=True)
    found = existing.first()
    if found is not None:
        return found
    policy = selectors.in_force(DocumentKind.PRIVACY_POLICY)
    if policy is None:
        raise PrivacyPolicyNotPublishedError()
    try:
        with transaction.atomic():
            return Consent.objects.create(user=user, kind=kind, legal_document=policy)
    except IntegrityError:  # the same person said yes on two devices at once
        return existing.get()


def withdraw_consent(user: User, kind: str) -> None:
    """Take a consent back. Nothing to do if it was not given."""
    Consent.objects.filter(user=user, kind=kind, withdrawn_at__isnull=True).update(
        withdrawn_at=timezone.now()
    )
