from typing import ClassVar

from allauth.account.adapter import DefaultAccountAdapter

from apps.users.accounts.managers import normalise_email


class AccountAdapter(DefaultAccountAdapter):  # type: ignore[misc]  # allauth has no type hints
    """Our changes to how django-allauth handles sign-up and login.

    allauth runs sign-up, login, email codes and password reset. This class is
    where we adjust its behaviour without copying its code.
    """

    # The words shoppers see (build E15): allauth's own, said more simply. The keys
    # (and so the error codes) are allauth's and do not change.
    error_messages: ClassVar[dict[str, str]] = {
        **DefaultAccountAdapter.error_messages,
        "account_inactive": "This account is switched off. Please contact us.",
        "cannot_remove_primary_email": "You can't remove your main email address.",
        "duplicate_email": "This email address is already on your account.",
        "email_password_mismatch": "That email and password don't match. Please try again.",
        "email_taken": "This email already has an account. Please log in instead.",
        "enter_current_password": "Please enter your current password.",
        "incorrect_code": "That code isn't right. Please check it and try again.",
        "incorrect_password": "That password isn't right. Please try again.",
        "invalid_or_expired_key": (
            "This code has expired or was already used. Please ask for a new one."
        ),
        "invalid_login": "We couldn't log you in. Please check your details and try again.",
        "invalid_password_reset": (
            "This reset code has expired or was already used. Please ask for a new one."
        ),
        "too_many_login_attempts": "Too many tries. Please wait a few minutes and try again.",
        "unknown_email": "We couldn't find an account with that email address.",
        "unverified_primary_email": "Please confirm your email address first.",
        "rate_limited": "You're going a little fast. Please wait a moment and try again.",
        "same_as_current": "Please choose something different from your current one.",
    }

    def clean_email(self, email: str) -> str:
        """Store every email in lowercase, as the users table requires."""
        return normalise_email(super().clean_email(email))
