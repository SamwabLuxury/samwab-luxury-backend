"""Error messages people can read (build E15; the lead, 25 Nov).

The web app shows ``detail`` and each field's ``message`` to shoppers, so they are
short, polite and free of technical words. Codes never change: only the words do.
These tests check every error class in the project, every general message, the
field messages, and allauth's login messages.
"""

import importlib
import pkgutil
from typing import Any

import pytest
from django.test import Client

import apps
from apps.platform.core.api.plain_words import GENERAL, TECHNICAL_WORDS, field_message
from apps.platform.core.exceptions import AppError
from apps.shop.listings.tests.helpers import make_live_listing
from apps.users.accounts.adapter import AccountAdapter
from apps.users.accounts.mfa_adapter import MFAAdapter
from apps.users.addresses.tests.helpers import make_user

# Errors that only machines or staff ever see.
NOT_FOR_SHOPPERS = {"webhook_signature_invalid"}


def every_error_class() -> list[type[AppError]]:
    for module in pkgutil.walk_packages(apps.__path__, "apps."):
        if module.name.endswith(".exceptions"):
            importlib.import_module(module.name)
    found: list[type[AppError]] = []
    todo = [AppError]
    while todo:
        cls = todo.pop()
        found.append(cls)
        todo.extend(cls.__subclasses__())
    return found


def plain(text: str) -> bool:
    lowered = f" {text.lower()}"
    return (
        not any(word in lowered for word in TECHNICAL_WORDS)
        and text.endswith(".")
        and len(text) <= 140
        and text[0].isupper()
    )


ERRORS = [cls for cls in every_error_class() if cls.code not in NOT_FOR_SHOPPERS]


def test_every_error_class_is_found() -> None:
    codes = {cls.code for cls in ERRORS}

    assert {"listing_unavailable", "drop_not_open", "invalid_link", "not_found"} <= codes
    assert len(ERRORS) >= 25


@pytest.mark.parametrize("error", ERRORS, ids=lambda cls: cls.code)
def test_every_error_message_is_plain(error: type[AppError]) -> None:
    assert plain(error.message), error.message


@pytest.mark.parametrize(("code", "text"), sorted(GENERAL.items()))
def test_every_general_message_is_plain(code: str, text: str) -> None:
    assert plain(text), text


@pytest.mark.parametrize(
    ("code", "framework_says", "people_read"),
    [
        ("required", "This field is required.", "Please fill this in."),
        ("blank", "This field may not be blank.", "Please fill this in."),
        ("null", "This field may not be null.", "Please fill this in."),
        ("invalid", "Enter a valid email address.", "Please enter a valid email address."),
        ("invalid", "Must be a valid UUID.", "This doesn't look right. Please check it."),
        ("invalid", "A valid integer is required.", "Please enter a number."),
        ("invalid", "A valid number is required.", "Please enter a number."),
        ("invalid", "Must be a valid boolean.", "This doesn't look right. Please check it."),
        ("invalid", "Not a valid string.", "This doesn't look right. Please check it."),
        (
            "invalid",
            "Enter a valid URL.",
            "Please enter a full web address, starting with https://.",
        ),
        (
            "invalid",
            "Date has wrong format. Use one of these formats instead: YYYY-MM-DD.",
            "Please enter a valid date.",
        ),
        ("invalid_choice", '"mint" is not a valid choice.', "Please choose one of the options."),
        (
            "does_not_exist",
            'Invalid pk "9" - object does not exist.',
            "Please choose one of the options.",
        ),
        (
            "max_length",
            "Ensure this field has no more than 160 characters.",
            "Please keep this to 160 characters or fewer.",
        ),
        (
            "min_length",
            "Ensure this field has at least 8 characters.",
            "Please use at least 8 characters.",
        ),
        (
            "max_length",
            "Ensure this field has no more than 3 elements.",
            "Please choose no more than 3.",
        ),
        (
            "max_value",
            "Ensure this value is less than or equal to 100.",
            "Please enter 100 or less.",
        ),
        (
            "min_value",
            "Ensure this value is greater than or equal to 0.",
            "Please enter 0 or more.",
        ),
        (
            "max_digits",
            "Ensure that there are no more than 12 digits in total.",
            "Please enter a smaller number.",
        ),
        (
            "not_a_list",
            'Expected a list of items but got type "str".',
            "Please choose at least one.",
        ),
        ("unique", "address with this label already exists.", "This is already in use."),
    ],
)
def test_framework_field_messages_become_plain(
    code: str, framework_says: str, people_read: str
) -> None:
    assert field_message(code, framework_says) == people_read


def test_a_message_we_wrote_for_people_is_kept() -> None:
    ours = "A drop must close after it opens."

    assert field_message("invalid", ours) == ours


@pytest.mark.parametrize("adapter", [AccountAdapter, MFAAdapter], ids=["account", "two-step"])
def test_allauth_messages_we_use_are_plain(adapter: Any) -> None:
    unused = {
        "phone_password_mismatch",
        "phone_taken",
        "unknown_phone",
        "username_blacklisted",
        "username_password_mismatch",
        "username_taken",
        "select_only_one",
        "max_email_addresses",
    }
    for key, text in adapter.error_messages.items():
        if key not in unused:
            assert plain(str(text)), (key, text)


# ---------- through the API, as the web app receives them ----------


@pytest.mark.django_db
def test_a_missing_field_reads_plainly(client: Client) -> None:
    body = client.post("/api/v1/mailing-list/", {}, content_type="application/json").json()

    assert body["code"] == "validation_error"
    assert body["detail"] == GENERAL["validation_error"]
    assert body["errors"] == [
        {"field": "email", "code": "required", "message": "Please fill this in."}
    ]


@pytest.mark.django_db
def test_broken_json_does_not_show_the_parser_message(client: Client) -> None:
    body = client.post("/api/v1/mailing-list/", "{not json", content_type="application/json").json()

    assert body["code"] == "parse_error"
    assert body["detail"] == GENERAL["parse_error"]


@pytest.mark.django_db
def test_a_bad_id_in_a_form_reads_plainly(client: Client) -> None:
    client.force_login(make_user())

    body = client.post(
        "/api/v1/orders/",
        {"listing_id": "abc", "payment_option": "pay_in_full", "delivery_choice": "buyer_courier"},
        content_type="application/json",
        headers={"Idempotency-Key": "k1"},
    ).json()

    message = next(e["message"] for e in body["errors"] if e["field"] == "listing_id")
    assert message == "This doesn't look right. Please check it."


@pytest.mark.django_db
def test_login_required_reads_plainly(client: Client) -> None:
    body = client.get("/api/v1/me/saved/").json()

    assert (body["code"], body["detail"]) == ("not_authenticated", "Please log in to continue.")


@pytest.mark.django_db
def test_an_unknown_address_reads_plainly(client: Client) -> None:
    body = client.get("/api/v1/no-such-page/").json()

    assert body["detail"] == GENERAL["not_found"]


@pytest.mark.django_db
def test_a_missing_piece_reads_plainly(client: Client) -> None:
    listing = make_live_listing()

    body = client.get(f"/api/v1/listings/{listing.pk}0/").json()

    assert body["detail"] == GENERAL["not_found"]


@pytest.mark.django_db
def test_a_wrong_password_reads_plainly(client: Client) -> None:
    make_user("ada@example.com")
    client.get("/_allauth/browser/v1/config")

    response = client.post(
        "/_allauth/browser/v1/auth/login",
        {"email": "ada@example.com", "password": "not-her-password"},
        content_type="application/json",
    )

    messages = [error["message"] for error in response.json()["errors"]]
    assert "That email and password don't match. Please try again." in messages
