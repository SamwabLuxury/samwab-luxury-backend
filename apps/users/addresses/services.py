"""Writes to addresses."""

from typing import Any

from django.db import transaction

from apps.users.accounts.models import User
from apps.users.addresses.exceptions import AddressLimitError
from apps.users.addresses.models import Address

# Enough for home, office, family and friends; stops one account filling the table.
MAX_ADDRESSES = 20


@transaction.atomic
def add_address(user: User, **fields: Any) -> Address:
    """Save a new address. The first one becomes the default; a new default replaces the old.

    The user's row is locked so two requests at once cannot both pass the limit or
    both become the default.
    """
    User.objects.select_for_update().filter(pk=user.pk).first()
    mine = Address.objects.filter(user=user)
    count = mine.count()
    if count >= MAX_ADDRESSES:
        raise AddressLimitError()
    address = Address(user=user, **fields)
    address.is_default = bool(fields.get("is_default")) or count == 0
    if address.is_default:  # undone with everything else if a check below fails
        mine.filter(is_default=True).update(is_default=False)
    address.full_clean()
    address.save()
    return address
