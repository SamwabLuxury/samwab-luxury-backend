"""Adding addresses: the default address, the limit, and the checks on each field."""

from typing import Any

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.addresses import services
from apps.addresses.exceptions import AddressLimitError
from apps.addresses.models import Address
from apps.addresses.tests.helpers import make_address, make_user

pytestmark = pytest.mark.django_db


def test_the_table_is_named_as_in_the_data_model() -> None:
    assert Address._meta.db_table == "addresses"
    columns = {field.column for field in Address._meta.concrete_fields}
    assert {"recipient_name_enc", "line1_enc", "line2_enc", "phone_enc"} <= columns


def test_the_first_address_becomes_the_default() -> None:
    first = make_address()
    second = make_address()

    assert first.is_default is True
    assert second.is_default is False


def test_a_new_default_replaces_the_old_one() -> None:
    first = make_address()
    second = make_address(is_default=True)

    first.refresh_from_db()
    assert (first.is_default, second.is_default) == (False, True)


def test_each_person_has_their_own_default() -> None:
    mine = make_address()
    theirs = make_address(make_user("chidi@example.com"))

    assert mine.is_default and theirs.is_default


def test_the_database_allows_one_default_per_person() -> None:
    address = make_address()

    with pytest.raises(IntegrityError), transaction.atomic():
        Address.objects.create(
            user=address.user,
            recipient_name="X",
            line1="Y",
            city="Lagos",
            country="NG",
            is_default=True,
        )


def test_there_is_a_limit_on_addresses() -> None:
    user = make_user()
    for _ in range(services.MAX_ADDRESSES):
        make_address(user)

    with pytest.raises(AddressLimitError) as refused:
        make_address(user)

    assert refused.value.code == "address_limit_reached"
    assert refused.value.status_code == 422


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("country", "Nigeria"),
        ("country", "ng"),
        ("recipient_name", ""),
        ("recipient_name", "A" * 161),
        ("line1", ""),
        ("phone", "call me maybe"),
        ("city", ""),
    ],
)
def test_bad_values_are_refused(field: str, value: str) -> None:
    bad: dict[str, Any] = {field: value}
    with pytest.raises(ValidationError) as refused:
        make_address(**bad)

    assert field in refused.value.message_dict
    assert not Address.objects.exists()


def test_optional_parts_may_be_left_out() -> None:
    address = make_address(line2=None, phone=None, region="", postal_code="", label="")

    address.refresh_from_db()
    assert (address.line2, address.phone) == (None, None)


def test_str_shows_no_street_or_name() -> None:
    address = make_address(label="Home")

    assert str(address) == "Home · Lagos, NG"
