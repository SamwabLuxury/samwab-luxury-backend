"""Helpers for the legal tests: a published text, an accepted one, a logged-in buyer."""

from django.test import Client

from apps.users.accounts.models import User
from apps.users.accounts.tests.helpers import make_staff
from apps.users.addresses.tests.helpers import make_user
from apps.users.legal import services
from apps.users.legal.models import LegalDocument

DOCUMENTS = "/api/v1/legal-documents/"
ACCEPT = "/api/v1/me/legal-acceptances/"
CONSENTS = "/api/v1/me/consents/"


def lawyer() -> User:
    """The staff member who writes and publishes the texts in these tests."""
    found = User.objects.filter(email="legal@samwab.com").first()
    return found or make_staff("legal@samwab.com")


def publish(kind: str, body: str = "", version: str = "") -> LegalDocument:
    """Publish a new version of ``kind`` with real (non-placeholder) wording."""
    draft = LegalDocument.objects.filter(kind=kind, effective_at__isnull=True).first()
    if draft is None:
        draft = services.new_draft(kind, by=lawyer())
    draft.body = body or f"The real {kind.replace('_', ' ')} text, version {version or 'next'}."
    if version:
        draft.version = version
    services.save_draft(draft, by=lawyer())
    return services.publish(draft, by=lawyer())


def accept(user: User, document: LegalDocument) -> None:
    services.accept(
        user,
        kind=document.kind,
        version=document.version,
        ip_address="203.0.113.9",
        user_agent="tests",
    )


def logged_in(client: Client, email: str = "ada@example.com") -> Client:
    client.force_login(make_user(email))
    return client
