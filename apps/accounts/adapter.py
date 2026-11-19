from allauth.account.adapter import DefaultAccountAdapter

from apps.accounts.managers import normalise_email


class AccountAdapter(DefaultAccountAdapter):  # type: ignore[misc]  # allauth has no type hints
    """Our changes to how django-allauth handles sign-up and login.

    allauth runs sign-up, login, email codes and password reset. This class is
    where we adjust its behaviour without copying its code.
    """

    def clean_email(self, email: str) -> str:
        """Store every email in lowercase, as the users table requires."""
        return normalise_email(super().clean_email(email))
