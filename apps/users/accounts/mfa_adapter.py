"""How allauth's two-step login stores its secrets.

allauth keeps each authenticator app's key (and the seed of the recovery codes) in
the ``mfa_authenticator`` table. Its default adapter stores them as plain text and
offers ``encrypt``/``decrypt`` as the hook to change that (allauth docs, "MFA:
Adapter"). We use the same Fernet keys as every other encrypted column (D40).
"""

from allauth.mfa.adapter import DefaultMFAAdapter

from apps.platform.core import encryption


class MFAAdapter(DefaultMFAAdapter):  # type: ignore[misc]  # allauth has no type hints
    def encrypt(self, text: str) -> str:
        return encryption.encrypt(text)

    def decrypt(self, encrypted_text: str) -> str:
        return encryption.decrypt(encrypted_text)
