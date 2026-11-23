from django.db.models import QuerySet

from apps.accounts.models import User
from apps.addresses.models import Address


def addresses_of(user: User) -> QuerySet[Address]:
    """A person's own addresses, newest first."""
    return Address.objects.filter(user=user)
