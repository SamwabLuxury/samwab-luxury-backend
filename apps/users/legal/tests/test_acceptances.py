"""Accepting a legal text: ``POST /api/v1/me/legal-acceptances/`` (in the contract).

One row per account per version, with the time, IP address and browser. Rows are never
changed or deleted. Only the version in force can be accepted, so nobody agrees to a
text that was already replaced.
"""

from typing import Any

import pytest
from django.db import IntegrityError, connection, transaction
from django.test import Client

from apps.shop.orders.tests.helpers import place_order
from apps.users.addresses.tests.helpers import make_address, make_user
from apps.users.legal import selectors
from apps.users.legal.enums import DocumentKind
from apps.users.legal.models import TermsAcceptance, TermsAcceptanceIsFinalError
from apps.users.legal.tests.helpers import ACCEPT, accept, logged_in, publish

pytestmark = pytest.mark.django_db

TERMS = DocumentKind.TERMS_OF_SERVICE


def post(client: Client, **body: object) -> Any:
    return client.post(
        ACCEPT, body, content_type="application/json", HTTP_USER_AGENT="Safari on iPhone"
    )


def test_accepting_the_version_in_force_is_recorded(client: Client) -> None:
    terms = publish(TERMS, version="1")

    response = post(logged_in(client), document_kind=TERMS, version="1")

    assert response.status_code == 201, response.content
    row = TermsAcceptance.objects.get()
    assert response.json() == {
        "id": str(row.pk),
        "document_kind": "terms_of_service",
        "version": "1",
        "accepted_at": row.accepted_at.isoformat().replace("+00:00", "Z"),
        "signed_name": None,
        "order_id": None,
    }
    assert (row.user.email, row.legal_document) == ("ada@example.com", terms)
    assert (row.ip_address, row.user_agent) == ("127.0.0.1", "Safari on iPhone")


def test_accepting_twice_keeps_the_first_record(client: Client) -> None:
    publish(TERMS, version="1")
    logged_in(client)

    first = post(client, document_kind=TERMS, version="1").json()
    again = post(client, document_kind=TERMS, version="1")

    assert again.status_code == 201
    assert again.json() == first
    assert TermsAcceptance.objects.count() == 1


def test_an_old_version_cannot_be_accepted(client: Client) -> None:
    publish(TERMS, version="1")
    publish(TERMS, version="2")

    response = post(logged_in(client), document_kind=TERMS, version="1")

    assert response.status_code == 409
    assert response.json()["code"] == "legal_document_not_current"
    assert not TermsAcceptance.objects.exists()


@pytest.mark.parametrize("version", ["1", "7"])
def test_a_draft_or_unknown_version_cannot_be_accepted(client: Client, version: str) -> None:
    response = post(logged_in(client), document_kind=TERMS, version=version)  # seed is a draft

    assert response.status_code == 409
    assert response.json()["code"] == "legal_document_not_current"


@pytest.mark.parametrize(
    "body",
    [{}, {"document_kind": "house_rules", "version": "1"}, {"document_kind": TERMS}],
)
def test_bad_input_is_refused(client: Client, body: dict[str, str]) -> None:
    response = post(logged_in(client), **body)

    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"


def test_login_is_required(client: Client) -> None:
    publish(TERMS, version="1")

    response = post(client, document_kind=TERMS, version="1")

    assert response.status_code == 401


def test_a_document_that_needs_a_signature_needs_the_typed_name(client: Client) -> None:
    publish(DocumentKind.CONSIGNMENT_AGREEMENT, version="1")
    logged_in(client)

    unsigned = post(client, document_kind="consignment_agreement", version="1")
    signed = post(
        client, document_kind="consignment_agreement", version="1", signed_name="  Adaeze Obi "
    )

    assert unsigned.status_code == 422
    assert unsigned.json()["code"] == "signed_name_required"
    assert signed.status_code == 201
    assert signed.json()["signed_name"] == "Adaeze Obi"


def test_the_buyer_authentication_form_is_signed_per_order(client: Client) -> None:
    publish(DocumentKind.BUYER_AUTHENTICATION_FORM, version="1")
    ada = make_user()
    order, _ = place_order(ada, shipping_address=make_address(ada))
    client.force_login(ada)
    form = {"document_kind": "buyer_authentication_form", "version": "1", "signed_name": "Ada"}

    without_order = post(client, **form)
    with_order = post(client, **form, order_id=str(order.pk))

    assert without_order.status_code == 422
    assert without_order.json()["code"] == "order_required"
    assert with_order.status_code == 201
    assert with_order.json()["order_id"] == str(order.pk)


def test_another_buyers_order_is_not_found(client: Client) -> None:
    publish(DocumentKind.BUYER_AUTHENTICATION_FORM, version="1")
    bea = make_user("bea@example.com")
    order, _ = place_order(bea, shipping_address=make_address(bea))

    response = post(
        logged_in(client),
        document_kind="buyer_authentication_form",
        version="1",
        signed_name="Ada",
        order_id=str(order.pk),
    )

    assert response.status_code == 404


def test_an_account_document_is_not_tied_to_an_order(client: Client) -> None:
    ada = make_user()
    order, _ = place_order(ada, shipping_address=make_address(ada))
    publish(TERMS, version="1")
    client.force_login(ada)

    response = post(client, document_kind=TERMS, version="1", order_id=str(order.pk))

    assert response.status_code == 422
    assert response.json()["code"] == "order_not_needed"


# ---------- what she still has to accept ----------


def test_missing_lists_texts_in_force_she_has_not_accepted() -> None:
    ada = make_user()
    terms = publish(TERMS, version="1")
    privacy = publish(DocumentKind.PRIVACY_POLICY, version="1")
    accept(ada, terms)

    assert selectors.missing(ada, [TERMS, DocumentKind.PRIVACY_POLICY]) == [privacy]
    assert selectors.missing(ada, [DocumentKind.RETURNS_POLICY]) == []  # none in force yet


def test_a_new_version_must_be_accepted_again() -> None:
    ada = make_user()
    accept(ada, publish(TERMS, version="1"))

    second = publish(TERMS, version="2")

    assert selectors.missing(ada, [TERMS]) == [second]


# ---------- append-only ----------


def test_an_acceptance_can_never_be_changed_or_deleted() -> None:
    ada = make_user()
    accept(ada, publish(TERMS))
    row = TermsAcceptance.objects.get()

    with pytest.raises(TermsAcceptanceIsFinalError):
        row.save()
    with pytest.raises(TermsAcceptanceIsFinalError):
        row.delete()
    with pytest.raises(TermsAcceptanceIsFinalError):
        TermsAcceptance.objects.update(user_agent="x")
    with pytest.raises(TermsAcceptanceIsFinalError):
        TermsAcceptance.objects.all().delete()


@pytest.mark.skipif(connection.vendor != "postgresql", reason="the trigger is PostgreSQL only")
def test_on_postgresql_the_database_refuses_changes_too() -> None:
    ada = make_user()
    accept(ada, publish(TERMS))

    with pytest.raises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("UPDATE terms_acceptances SET user_agent = 'x'")
    with pytest.raises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("DELETE FROM terms_acceptances")


def test_the_database_keeps_one_row_per_account_and_version() -> None:
    ada = make_user()
    terms = publish(TERMS)
    accept(ada, terms)

    with pytest.raises(IntegrityError), transaction.atomic():
        TermsAcceptance.objects.create(user=ada, legal_document=terms, ip_address="203.0.113.9")
