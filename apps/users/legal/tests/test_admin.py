"""The legal texts in the admin: staff replace a placeholder, then publish it.

Superusers only for now (which staff role writes legal texts is a question for the
owners). Acceptances and consents are evidence, so their screens are read-only.
"""

from typing import Any

import pytest
from django.contrib.messages import get_messages
from django.test import Client

from apps.shop.listings.tests.helpers import make_admin
from apps.users.accounts import roles
from apps.users.accounts.tests.helpers import admin_login, make_staff
from apps.users.addresses.tests.helpers import make_user
from apps.users.legal.enums import DocumentKind
from apps.users.legal.models import LegalDocument
from apps.users.legal.tests.helpers import accept, publish

pytestmark = pytest.mark.django_db

ADMIN = "/admin/legal"


@pytest.fixture
def boss_client(client: Client) -> Client:
    admin_login(client, make_admin())
    return client


def draft(kind: str = DocumentKind.TERMS_OF_SERVICE) -> LegalDocument:
    return LegalDocument.objects.get(kind=kind, effective_at__isnull=True)


def notes(response: Any) -> list[str]:
    return [str(message) for message in get_messages(response.wsgi_request)]


def act(client: Client, action: str, document: LegalDocument) -> Any:
    return client.post(
        f"{ADMIN}/legaldocument/",
        {"action": action, "_selected_action": [str(document.pk)]},
        follow=True,
    )


@pytest.mark.parametrize("screen", ["legaldocument", "termsacceptance", "consent"])
def test_the_screens_open(boss_client: Client, screen: str) -> None:
    assert boss_client.get(f"{ADMIN}/{screen}/").status_code == 200


def test_staff_type_the_real_text_into_the_draft(boss_client: Client) -> None:
    document = draft()

    response = boss_client.post(
        f"{ADMIN}/legaldocument/{document.pk}/change/",
        {"version": "1", "body": "The real terms.\r\nLine two."},
    )

    assert response.status_code == 302, response.content
    document.refresh_from_db()
    assert document.body == "The real terms.\nLine two."
    assert document.is_draft


def test_publishing_a_placeholder_is_refused_in_plain_words(boss_client: Client) -> None:
    response = act(boss_client, "publish_selected", draft())

    assert any("still has placeholder wording" in note for note in notes(response))
    assert draft().is_draft


def test_publishing_from_the_list(boss_client: Client) -> None:
    document = draft()
    document.body = "The real terms."
    document.save()

    response = act(boss_client, "publish_selected", document)

    document.refresh_from_db()
    assert document.is_in_force
    assert any("Published Terms of service, version 1" in note for note in notes(response))


def test_a_published_text_is_read_only(boss_client: Client) -> None:
    published = publish(DocumentKind.TERMS_OF_SERVICE)

    page = boss_client.get(f"{ADMIN}/legaldocument/{published.pk}/change/")

    assert page.status_code == 200
    assert page.context["has_change_permission"] is False
    assert page.context["has_delete_permission"] is False


def test_new_draft_and_retire_from_the_list(boss_client: Client) -> None:
    published = publish(DocumentKind.TERMS_OF_SERVICE)

    act(boss_client, "new_draft_selected", published)
    act(boss_client, "retire_selected", published)

    published.refresh_from_db()
    assert published.retired_at is not None
    assert draft().version == "2"


def test_a_draft_is_deleted_through_the_service(boss_client: Client) -> None:
    document = draft()

    boss_client.post(f"{ADMIN}/legaldocument/{document.pk}/delete/", {"post": "yes"})

    assert not LegalDocument.objects.filter(pk=document.pk).exists()


def test_a_new_text_is_added_as_a_draft(boss_client: Client) -> None:
    response = boss_client.post(
        f"{ADMIN}/legaldocument/add/",
        {"kind": "storage_terms", "version": "1", "body": "Storage terms."},
    )

    assert response.status_code == 302, response.content
    added = LegalDocument.objects.get(kind="storage_terms")
    assert added.is_draft
    assert len(added.body_sha256) == 64


def test_acceptances_and_consents_cannot_be_added_changed_or_deleted(boss_client: Client) -> None:
    accept(make_user(), publish(DocumentKind.TERMS_OF_SERVICE))
    row = make_user().terms_acceptances.get()

    assert boss_client.get(f"{ADMIN}/termsacceptance/add/").status_code == 403
    assert boss_client.get(f"{ADMIN}/consent/add/").status_code == 403
    page = boss_client.get(f"{ADMIN}/termsacceptance/{row.pk}/change/")
    assert page.context["has_change_permission"] is False
    assert page.context["has_delete_permission"] is False


def test_staff_without_a_grant_cannot_open_the_legal_screens(client: Client) -> None:
    admin_login(client, make_staff("intake@samwab.com", roles.INTAKE_STAFF))

    assert client.get(f"{ADMIN}/legaldocument/").status_code == 403


def test_the_menu_lists_the_legal_screens_for_superusers(boss_client: Client) -> None:
    text = boss_client.get("/admin/").content.decode()

    assert "Legal texts" in text
    assert "Terms accepted" in text
