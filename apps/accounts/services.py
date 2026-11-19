"""Changes to users. Views call these; they never change a user themselves."""

from typing import Any

from django.db import transaction

from apps.accounts.models import User

# The profile fields a user may change about herself.
PROFILE_FIELDS = ("first_name", "last_name", "country", "locale", "timezone")


@transaction.atomic
def update_profile(*, user: User, changes: dict[str, Any]) -> User:
    """Change the user's own profile. ``changes`` has already been validated."""
    unknown = set(changes) - set(PROFILE_FIELDS)
    if unknown:
        raise ValueError(f"Not profile fields: {sorted(unknown)}")
    if not changes:
        return user

    for field, value in changes.items():
        setattr(user, field, value)
    user.save(update_fields=[*changes, "updated_at"])
    return user
