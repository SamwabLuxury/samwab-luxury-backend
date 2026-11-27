"""Reading the texts in force (no login), consents, and terms at sign-up.

``GET /api/v1/legal-documents/`` and ``/{kind}/`` are contract additions: the web app
needs the words to show before anyone can accept them.
"""

from typing import Any

import pytest
from django.test import Client

from apps.users.accounts.models import User
from apps.users.accounts.tests.helpers import sign_up, sign_up_and_verify
from apps.users.addresses.tests.helpers import make_user
from apps.users.legal.enums import ConsentKind, DocumentKind
from apps.users.legal.models import Consent, TermsAcceptance
from apps.users.legal.tests.helpers import CONSENTS, DOCUMENTS, accept, logged_in, publish

pytestmark = pytest.mark.django_db

TERMS = DocumentKind.TERMS_OF_SERVICE
PRIVACY = DocumentKind.PRIVACY_POLICY


# ---------- the texts in force ----------


def test_the_list_shows_only_texts_in_force(client: Client) -> None:
    terms = publish(TERMS, version="1")

    response = client.get(DOCUMENTS)

    assert response.status_code == 200
    assert response.json()["results"] == [
        {
            "kind": "terms_of_service",
            "title": "Terms of service",
            "version": "1",
            "effective_at": terms.effective_at.isoformat().replace("+00:00", "Z"),  # type: ignore[union-attr]
            "body_sha256": terms.body_sha256,
            "accepted": None,
        }
    ]


def test_with_nothing_published_the_list_is_empty(client: Client) -> None:
    assert client.get(DOCUMENTS).json()["results"] == []


def test_a_logged_in_reader_sees_what_she_has_accepted(client: Client) -> None:
    ada = make_user()
    accept(ada, publish(TERMS))
    publish(DocumentKind.RETURNS_POLICY)
    client.force_login(ada)

    rows = client.get(DOCUMENTS).json()["results"]

    assert {row["kind"]: row["accepted"] for row in rows} == {
        "returns_policy": False,
        "terms_of_service": True,
    }


def test_one_text_with_its_words(client: Client) -> None:
    terms = publish(TERMS, body="Our terms.\n\n1. Be kind.", version="1")

    response = client.get(f"{DOCUMENTS}terms_of_service/")

    assert response.status_code == 200
    body = response.json()
    assert (body["version"], body["body"], body["title"]) == (
        "1",
        "Our terms.\n\n1. Be kind.",
        "Terms of service",
    )
    assert body["body_sha256"] == terms.body_sha256


@pytest.mark.parametrize("kind", ["terms_of_service", "house_rules"])
def test_a_kind_with_nothing_in_force_is_not_found(client: Client, kind: str) -> None:
    response = client.get(f"{DOCUMENTS}{kind}/")

    assert response.status_code == 404


def test_reading_needs_no_csrf_or_login_and_writing_is_not_allowed(client: Client) -> None:
    response = client.post(DOCUMENTS, {}, content_type="application/json")

    assert response.status_code == 405


# ---------- consents ----------


def consents(client: Client) -> dict[str, Any]:
    return {row["kind"]: row for row in client.get(CONSENTS).json()["results"]}


def test_consents_start_off(client: Client) -> None:
    rows = consents(logged_in(client))

    assert rows == {
        "marketing": {"kind": "marketing", "granted": False, "granted_at": None},
        "training_images": {"kind": "training_images", "granted": False, "granted_at": None},
    }


def test_giving_and_withdrawing_a_consent(client: Client) -> None:
    privacy = publish(PRIVACY, version="1")
    logged_in(client)

    given = client.put(f"{CONSENTS}training_images/")
    again = client.put(f"{CONSENTS}training_images/")
    withdrawn = client.delete(f"{CONSENTS}training_images/")

    assert given.status_code == 200
    assert given.json()["granted"] is True
    assert again.json() == given.json()  # the first time is kept
    assert withdrawn.status_code == 204
    row = Consent.objects.get()
    assert (row.kind, row.legal_document, row.withdrawn_at is not None) == (
        "training_images",
        privacy,
        True,
    )
    assert consents(client)["training_images"]["granted"] is False


def test_consent_given_again_after_withdrawing_is_a_new_record(client: Client) -> None:
    publish(PRIVACY)
    logged_in(client)
    client.put(f"{CONSENTS}marketing/")
    client.delete(f"{CONSENTS}marketing/")

    client.put(f"{CONSENTS}marketing/")

    assert Consent.objects.count() == 2
    assert Consent.objects.filter(withdrawn_at__isnull=True).count() == 1


def test_withdrawing_what_was_never_given_is_fine(client: Client) -> None:
    assert logged_in(client).delete(f"{CONSENTS}marketing/").status_code == 204


def test_consent_waits_for_a_published_privacy_policy(client: Client) -> None:
    response = logged_in(client).put(f"{CONSENTS}marketing/")

    assert response.status_code == 409
    assert response.json()["code"] == "privacy_policy_not_published"
    assert not Consent.objects.exists()


def test_an_unknown_consent_is_not_found(client: Client) -> None:
    publish(PRIVACY)

    assert logged_in(client).put(f"{CONSENTS}selling_data/").status_code == 404


def test_consents_need_login(client: Client) -> None:
    assert client.get(CONSENTS).status_code == 401
    assert client.put(f"{CONSENTS}marketing/").status_code == 401


def test_each_account_sees_only_her_own_consents(client: Client) -> None:
    publish(PRIVACY)
    logged_in(client, "bea@example.com").put(f"{CONSENTS}marketing/")

    assert consents(logged_in(client))["marketing"]["granted"] is False


def test_two_devices_saying_yes_at_once_keep_one_consent(monkeypatch: pytest.MonkeyPatch) -> None:
    from apps.users.legal import selectors, services

    ada = make_user()
    policy = publish(PRIVACY)
    real_in_force = selectors.in_force

    def other_device_first(kind: str) -> object:
        Consent.objects.create(user=ada, kind="marketing", legal_document=policy)
        return real_in_force(kind)

    monkeypatch.setattr(selectors, "in_force", other_device_first)

    consent = services.grant_consent(ada, "marketing")

    assert Consent.objects.get() == consent
    assert str(consent) == "Marketing emails (given)"


def test_consent_kinds_match_the_data_model() -> None:
    assert sorted(ConsentKind.values) == ["marketing", "training_images"]


# ---------- terms at sign-up ----------


def test_ticking_the_box_at_sign_up_accepts_the_texts_in_force(client: Client) -> None:
    terms = publish(TERMS, version="1")
    privacy = publish(PRIVACY, version="1")

    sign_up(client, terms_accepted=True)

    ada = User.objects.get(email="ada@example.com")
    accepted = set(
        TermsAcceptance.objects.filter(user=ada).values_list("legal_document", flat=True)
    )
    assert accepted == {terms.pk, privacy.pk}
    assert TermsAcceptance.objects.filter(ip_address="127.0.0.1").count() == 2


def test_without_the_box_nothing_is_accepted_and_the_step_waits(client: Client) -> None:
    publish(TERMS)

    sign_up_and_verify(client)

    assert not TermsAcceptance.objects.exists()
    assert client.get("/api/v1/me/").json()["next_steps"] == ["accept_terms"]


def test_the_step_goes_once_the_terms_are_accepted(client: Client) -> None:
    terms = publish(TERMS, version="1")
    sign_up_and_verify(client)

    client.post(
        "/api/v1/me/legal-acceptances/",
        {"document_kind": "terms_of_service", "version": "1"},
        content_type="application/json",
    )

    assert terms.acceptances.count() == 1
    assert client.get("/api/v1/me/").json()["next_steps"] == []


def test_with_nothing_published_sign_up_works_as_before(client: Client) -> None:
    response = sign_up(client, terms_accepted=True)

    assert response.status_code == 401  # verification code sent, as always
    assert not TermsAcceptance.objects.exists()


def test_an_owner_keeps_accept_terms_until_she_signs_the_consignment_agreement() -> None:
    from apps.users.accounts import selectors as accounts

    owner = make_user("olu@example.com")
    owner.signup_intent = "owner"
    owner.save()
    agreement = publish(DocumentKind.CONSIGNMENT_AGREEMENT, version="1")

    assert accounts.get_next_steps(owner)[0] == "accept_terms"

    TermsAcceptance.objects.create(
        user=owner, legal_document=agreement, ip_address="203.0.113.9", signed_name="Olu"
    )

    assert "accept_terms" not in accounts.get_next_steps(owner)
