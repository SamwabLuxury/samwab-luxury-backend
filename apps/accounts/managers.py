from typing import TYPE_CHECKING, Any

from django.contrib.auth.base_user import BaseUserManager

if TYPE_CHECKING:
    from apps.accounts.models import User


def normalise_email(email: str) -> str:
    """Trim spaces and make the whole address lowercase.

    People type the same address in different ways ("Ada@Example.com ").
    Storing one form means one person cannot end up with two accounts.
    """
    return email.strip().lower()


class UserManager(BaseUserManager["User"]):
    """Creates users. People log in with their email address; there is no username."""

    use_in_migrations = True

    def _create(self, email: str, password: str | None, **fields: Any) -> "User":
        if not isinstance(email, str) or not normalise_email(email):
            raise ValueError("An email address is required.")
        user = self.model(email=normalise_email(email), **fields)
        # A user without a password cannot log in with one until they set it.
        user.set_password(password)
        user.full_clean(exclude=["password"])
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **fields: Any) -> "User":
        """Create a normal user. They are never staff, whatever is passed in."""
        fields["is_staff"] = False
        fields["is_superuser"] = False
        return self._create(email, password, **fields)

    def create_superuser(self, email: str, password: str | None = None, **fields: Any) -> "User":
        """Create a user who can do everything in the admin. Used by ``createsuperuser``."""
        if not password:
            raise ValueError("A superuser needs a password.")
        fields["is_staff"] = True
        fields["is_superuser"] = True
        return self._create(email, password, **fields)

    def get_by_natural_key(self, email: str | None) -> "User":
        """Find a user at login. The email is matched in any letter case."""
        return self.get(email=normalise_email(email or ""))
