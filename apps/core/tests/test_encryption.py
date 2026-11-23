"""Encrypting single values for the database (decision D5): keys, rotation, the field."""

import pytest
from cryptography.fernet import Fernet
from django.core.checks import Error
from django.core.exceptions import FieldError
from django.db import connection
from django.test import override_settings

from apps.core import encryption
from apps.core.checks import check_field_encryption_keys
from apps.core.fields import EncryptedTextField

OLD = Fernet.generate_key().decode()
NEW = Fernet.generate_key().decode()


def test_a_value_comes_back_as_it_went_in() -> None:
    stored = encryption.encrypt("12 Admiralty Way, Lekki")

    assert "Admiralty" not in stored
    assert encryption.decrypt(stored) == "12 Admiralty Way, Lekki"


def test_the_same_value_encrypts_differently_each_time() -> None:
    assert encryption.encrypt("Lagos") != encryption.encrypt("Lagos")


def test_the_first_key_encrypts_and_every_key_decrypts() -> None:
    with override_settings(FIELD_ENCRYPTION_KEYS=[OLD]):
        written_long_ago = encryption.encrypt("Ikoyi")

    with override_settings(FIELD_ENCRYPTION_KEYS=[NEW, OLD]):
        assert encryption.decrypt(written_long_ago) == "Ikoyi"
        fresh = encryption.encrypt("Ikoyi")

    with override_settings(FIELD_ENCRYPTION_KEYS=[NEW]):
        assert encryption.decrypt(fresh) == "Ikoyi"
        with pytest.raises(encryption.EncryptionKeyError, match="cannot be decrypted"):
            encryption.decrypt(written_long_ago)


def test_without_keys_nothing_is_encrypted() -> None:
    with (
        override_settings(FIELD_ENCRYPTION_KEYS=[]),
        pytest.raises(encryption.EncryptionKeyError, match="DJANGO_FIELD_ENCRYPTION_KEYS"),
    ):
        encryption.encrypt("Lagos")


@pytest.mark.parametrize(
    ("keys", "problem"),
    [
        ([], "DJANGO_FIELD_ENCRYPTION_KEYS is empty"),
        (["not-a-key"], "Key 1 in DJANGO_FIELD_ENCRYPTION_KEYS is not a valid Fernet key"),
        ([NEW, "short"], "Key 2 in DJANGO_FIELD_ENCRYPTION_KEYS is not a valid Fernet key"),
    ],
)
def test_the_system_check_names_a_bad_key_without_showing_it(keys: list[str], problem: str) -> None:
    with override_settings(FIELD_ENCRYPTION_KEYS=keys):
        [error] = check_field_encryption_keys(None)

    assert isinstance(error, Error)
    assert error.id == "core.E001"
    assert problem in error.msg
    assert "short" not in error.msg and "not-a-key" not in error.msg


def test_good_keys_pass_the_system_check() -> None:
    with override_settings(FIELD_ENCRYPTION_KEYS=[NEW, OLD]):
        assert check_field_encryption_keys(None) == []


def test_the_field_cannot_be_searched_or_sorted_on() -> None:
    from apps.addresses.models import Address

    with pytest.raises(FieldError, match="encrypted"):
        Address.objects.filter(**{"line1": "12 Admiralty Way"})
    with pytest.raises(FieldError, match="encrypted"):
        Address.objects.filter(**{"line1__icontains": "Admiralty"})
    with pytest.raises(FieldError, match="encrypted"):
        Address.objects.filter(**{"line1__lower__exact": "admiralty"})
    assert str(Address.objects.filter(**{"line2__isnull": True}).query)  # only "is it empty?" works


def test_the_field_checks_the_length_of_the_plain_text() -> None:
    from apps.addresses.models import Address

    field = Address._meta.get_field("recipient_name")

    assert isinstance(field, EncryptedTextField)
    assert [getattr(v, "limit_value", None) for v in field.validators] == [160]


@pytest.mark.django_db
def test_the_database_holds_only_ciphertext() -> None:
    from apps.addresses.tests.helpers import make_address

    address = make_address(
        recipient_name="Adaeze Obi", line1="12 Admiralty Way", phone="+234 803 000 0000"
    )

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT recipient_name_enc, line1_enc, phone_enc, city FROM addresses WHERE id = %s",
            [address.pk.hex if connection.vendor == "sqlite" else address.pk],
        )
        name, line1, phone, city = cursor.fetchone()

    assert "Adaeze" not in name and "Admiralty" not in line1 and "803" not in phone
    assert city == "Lagos"  # city, region, postal code and country stay searchable
    address.refresh_from_db()
    assert (address.recipient_name, address.line1, address.phone) == (
        "Adaeze Obi",
        "12 Admiralty Way",
        "+234 803 000 0000",
    )


@pytest.mark.django_db
def test_reencrypt_fields_moves_every_row_to_the_first_key() -> None:
    from django.core.management import call_command

    from apps.addresses.models import Address
    from apps.addresses.tests.helpers import make_address

    with override_settings(FIELD_ENCRYPTION_KEYS=[OLD]):
        address = make_address(line1="1 Bourdillon Road")

    with override_settings(FIELD_ENCRYPTION_KEYS=[NEW, OLD]):
        call_command("reencrypt_fields", verbosity=0)

    with override_settings(FIELD_ENCRYPTION_KEYS=[NEW]):
        assert Address.objects.get(pk=address.pk).line1 == "1 Bourdillon Road"
