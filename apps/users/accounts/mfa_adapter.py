"""How allauth's two-step login stores its secrets.

allauth keeps each authenticator app's key (and the seed of the recovery codes) in
the ``mfa_authenticator`` table. Its default adapter stores them as plain text and
offers ``encrypt``/``decrypt`` as the hook to change that (allauth docs, "MFA:
Adapter"). We use the same Fernet keys as every other encrypted column (D40).
"""

from typing import ClassVar

from allauth.mfa.adapter import DefaultMFAAdapter

from apps.platform.core import encryption


class MFAAdapter(DefaultMFAAdapter):  # type: ignore[misc]  # allauth has no type hints
    # The words people see (build E15); the keys are allauth's and do not change.
    error_messages: ClassVar[dict[str, str]] = {
        **DefaultMFAAdapter.error_messages,
        "add_email_blocked": "You can't add an email address while two-step login is on.",
        "cannot_delete_authenticator": "Two-step login can't be turned off for this account.",
        "cannot_generate_recovery_codes": (
            "Turn on two-step login first, then you can make recovery codes."
        ),
        "incorrect_code": "That code isn't right. Please check your app and try again.",
        "unverified_email": "Please confirm your email address before turning on two-step login.",
    }

    def encrypt(self, text: str) -> str:
        return encryption.encrypt(text)

    def decrypt(self, encrypted_text: str) -> str:
        return encryption.decrypt(encrypted_text)
