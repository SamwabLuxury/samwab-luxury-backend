"""Changes to users. Views call these; they never change a user themselves."""

from typing import Any

from django.db import transaction

from apps.accounts.models import User
from apps.audit import services as audit

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


# ---------- staff changes in the admin site ----------

# Never in an audit event: the password hash, and the login time, which changes on its own.
_NOT_AUDITED = ("password", "last_login")
# Roles are groups, so a role given or taken shows up here.
_AUDITED_LISTS = ("groups", "user_permissions")


def staff_view_of(user: User) -> audit.Snapshot:
    """What an audit event records about an account: details, flags, roles and permissions."""
    return audit.snapshot(user, exclude=_NOT_AUDITED, many=_AUDITED_LISTS)


def record_staff_edit(user: User, *, before: audit.Snapshot | None, by: User) -> None:
    """Record an account a staff member added (``before`` is ``None``) or changed."""
    audit.record_saved(user, before=before, by=by, exclude=_NOT_AUDITED, many=_AUDITED_LISTS)
