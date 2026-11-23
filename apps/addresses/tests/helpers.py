from typing import Any

from apps.accounts.models import User
from apps.addresses import services
from apps.addresses.models import Address


def make_user(email: str = "ada@example.com") -> User:
    found = User.objects.filter(email=email).first()
    return found or User.objects.create_user(email, "correct-horse-battery-9")


def make_address(user: User | None = None, **fields: Any) -> Address:
    """A delivery address in Lagos, saved through the service."""
    fields = {
        "recipient_name": "Adaeze Obi",
        "line1": "12 Admiralty Way",
        "city": "Lagos",
        "region": "Lagos",
        "postal_code": "106104",
        "country": "NG",
        **fields,
    }
    return services.add_address(user or make_user(), **fields)
