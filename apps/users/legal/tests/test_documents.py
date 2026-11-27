"""Legal texts: drafts, publishing, one version in force per kind, and texts that never change.

The owners (or their lawyer) write the wording. Until they do, the terms of service,
privacy policy and returns policy exist as placeholder drafts that cannot be published.
"""

import hashlib

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.platform.audit.models import AuditEvent
from apps.users.legal import selectors, services
from apps.users.legal.enums import DocumentKind
from apps.users.legal.exceptions import (
    DraftAlreadyExistsError,
    LegalDocumentNotDraftError,
    LegalDocumentNotInForceError,
    PlaceholderTextError,
)
from apps.users.legal.models import LegalDocument
from apps.users.legal.tests.helpers import lawyer, publish

pytestmark = pytest.mark.django_db

TERMS = DocumentKind.TERMS_OF_SERVICE


def seeded_draft(kind: str = TERMS) -> LegalDocument:
    return LegalDocument.objects.get(kind=kind, effective_at__isnull=True)


# ---------- the placeholder drafts ----------


@pytest.mark.parametrize(
    "kind",
    [DocumentKind.TERMS_OF_SERVICE, DocumentKind.PRIVACY_POLICY, DocumentKind.RETURNS_POLICY],
)
def test_three_placeholder_drafts_wait_for_the_owners_wording(kind: str) -> None:
    draft = seeded_draft(kind)

    assert draft.version == "1"
    assert draft.is_draft
    assert services.PLACEHOLDER_MARK in draft.body
    assert selectors.in_force(kind) is None  # nothing is in force, so nothing is asked


def test_a_placeholder_cannot_be_published() -> None:
    with pytest.raises(PlaceholderTextError):
        services.publish(seeded_draft(), by=lawyer())

    assert seeded_draft().is_draft


def test_staff_replace_the_placeholder_then_publish() -> None:
    draft = seeded_draft()
    draft.body = "Welcome to Samwab.\r\n\r\nThese are our terms.  \n"

    services.save_draft(draft, by=lawyer())
    published = services.publish(draft, by=lawyer())

    assert published.is_in_force
    assert published.effective_at is not None
    assert published.body == "Welcome to Samwab.\n\nThese are our terms."  # tidied once
    expected = hashlib.sha256(published.body.encode()).hexdigest()
    assert published.body_sha256 == expected
    assert selectors.in_force(TERMS) == published


# ---------- versions ----------


def test_publishing_a_new_version_retires_the_one_in_force() -> None:
    first = publish(TERMS, version="1")

    second = publish(TERMS, body="Terms, second edition.")

    first.refresh_from_db()
    assert second.version == "2"
    assert first.retired_at == second.effective_at
    assert not first.is_in_force
    assert selectors.in_force(TERMS) == second


def test_a_new_draft_starts_from_the_text_in_force() -> None:
    current = publish(TERMS, body="Terms, first edition.", version="1")

    draft = services.new_draft(TERMS, by=lawyer())

    assert (draft.version, draft.body, draft.is_draft) == ("2", current.body, True)


def test_only_one_draft_per_kind_at_a_time() -> None:
    with pytest.raises(DraftAlreadyExistsError):
        services.new_draft(TERMS, by=lawyer())  # the seeded placeholder is still a draft


def test_the_database_also_refuses_a_second_draft() -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        LegalDocument.objects.create(kind=TERMS, version="9", body="x", body_sha256="0" * 64)


def test_the_database_refuses_two_texts_in_force_for_one_kind() -> None:
    publish(TERMS, version="1")
    other = LegalDocument.objects.create(
        kind=TERMS, version="2", body="x", body_sha256="0" * 64, effective_at=None
    )
    other.effective_at = selectors.in_force(TERMS).effective_at  # type: ignore[union-attr]

    with pytest.raises(IntegrityError), transaction.atomic():
        other.save()


def test_versions_are_unique_per_kind() -> None:
    publish(TERMS, version="1")
    services.new_draft(TERMS, by=lawyer())

    with pytest.raises(IntegrityError), transaction.atomic():
        LegalDocument.objects.filter(kind=TERMS, effective_at__isnull=True).update(version="1")


def test_a_first_text_for_a_kind_with_no_seed_starts_at_version_1() -> None:
    draft = services.new_draft(DocumentKind.STORAGE_TERMS, by=lawyer())

    assert (draft.version, draft.is_draft) == ("1", True)
    assert services.PLACEHOLDER_MARK in draft.body


def test_a_version_number_typed_by_staff_is_kept() -> None:
    published = publish(TERMS, version="2026-11")

    assert published.version == "2026-11"
    assert services.new_draft(TERMS, by=lawyer()).version == "2"


# ---------- texts that never change ----------


def test_a_published_text_cannot_be_edited() -> None:
    published = publish(TERMS)
    published.body = "Something else."

    with pytest.raises(LegalDocumentNotDraftError):
        services.save_draft(published, by=lawyer())

    published.refresh_from_db()
    assert published.body != "Something else."


def test_only_a_draft_can_be_published() -> None:
    published = publish(TERMS)

    with pytest.raises(LegalDocumentNotDraftError):
        services.publish(published, by=lawyer())


def test_an_empty_text_cannot_be_saved() -> None:
    draft = seeded_draft()
    draft.body = "  \r\n "

    with pytest.raises(ValidationError):
        services.save_draft(draft, by=lawyer())


def test_retiring_leaves_no_text_in_force() -> None:
    published = publish(TERMS)

    services.retire(published, by=lawyer())

    published.refresh_from_db()
    assert published.retired_at is not None
    assert selectors.in_force(TERMS) is None


def test_only_the_text_in_force_can_be_retired() -> None:
    with pytest.raises(LegalDocumentNotInForceError):
        services.retire(seeded_draft(), by=lawyer())


def test_only_drafts_can_be_deleted() -> None:
    published = publish(TERMS)

    with pytest.raises(LegalDocumentNotDraftError):
        services.delete_draft(published, by=lawyer())

    draft = services.new_draft(TERMS, by=lawyer())
    services.delete_draft(draft, by=lawyer())
    assert not LegalDocument.objects.filter(pk=draft.pk).exists()


# ---------- audit ----------


def test_every_change_is_in_the_audit_log() -> None:
    draft = seeded_draft()
    draft.body = "Real terms."
    services.save_draft(draft, by=lawyer())
    services.publish(draft, by=lawyer())
    services.retire(draft, by=lawyer())

    actions = list(
        AuditEvent.objects.filter(object_id=draft.pk)
        .order_by("id")
        .values_list("action", flat=True)
    )
    assert actions == [
        "legal.legaldocument.changed",
        "legal.legaldocument.published",
        "legal.legaldocument.retired",
    ]
    event = AuditEvent.objects.get(action="legal.legaldocument.published")
    assert event.actor == lawyer()
    assert event.changes["version"] == "1"
    assert event.changes["body_sha256"] == draft.body_sha256


def test_publishing_records_the_version_it_replaced() -> None:
    publish(TERMS, version="1")
    publish(TERMS)

    retired = AuditEvent.objects.filter(action="legal.legaldocument.retired").get()
    assert retired.changes["replaced_by"] == "2"


def test_a_save_that_changes_nothing_writes_no_event() -> None:
    draft = seeded_draft()
    services.save_draft(draft, by=lawyer())

    assert not AuditEvent.objects.filter(object_id=draft.pk).exists()


def test_title_is_the_kind_in_words() -> None:
    assert seeded_draft(DocumentKind.RETURNS_POLICY).title == "Returns policy"
    assert str(seeded_draft()) == "Terms of service, version 1 (draft)"
