"""Encrypting single values for the database (decision D5).

Values are encrypted with Fernet from the ``cryptography`` package (AES with an
HMAC, so a changed value is detected). The keys come from the setting
``FIELD_ENCRYPTION_KEYS`` (environment variable ``DJANGO_FIELD_ENCRYPTION_KEYS``,
comma-separated), never from ``SECRET_KEY``:

- the **first** key encrypts; **every** key can decrypt;
- to change keys, put a new key first, run ``python manage.py reencrypt_fields``,
  then remove the old key.

Losing every key means losing the data. Fernet tokens carry their creation time
in plain text and grow with the value's length; neither reveals the value.
"""

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings

SETTING = "DJANGO_FIELD_ENCRYPTION_KEYS"

# Used on developers' machines when .env has no key. It is in Git, so it protects
# nothing; production settings refuse it.
LOCAL_ONLY_ENCRYPTION_KEY = "W4yqidRta6o9bL85N2iTe154V7IxWgaWoW-j41siGbE="


class EncryptionKeyError(Exception):
    """The keys are missing, or none of them opens a stored value."""


def key_problems(keys: list[str]) -> list[str]:
    """What is wrong with these keys, without ever showing a key."""
    if not keys:
        return [f"{SETTING} is empty."]
    problems = []
    for number, key in enumerate(keys, start=1):
        try:
            Fernet(key)
        except (ValueError, TypeError):
            problems.append(
                f"Key {number} in {SETTING} is not a valid Fernet key "
                "(32 bytes, URL-safe base64, as Fernet.generate_key() makes)."
            )
    return problems


@lru_cache(maxsize=4)
def _fernet_for(keys: tuple[str, ...]) -> MultiFernet:
    problems = key_problems(list(keys))
    if problems:
        raise EncryptionKeyError(" ".join(problems))
    return MultiFernet([Fernet(key) for key in keys])


def _fernet() -> MultiFernet:
    return _fernet_for(tuple(settings.FIELD_ENCRYPTION_KEYS))


def encrypt(text: str) -> str:
    """Encrypt with the first key. The same text gives a different token each time."""
    return _fernet().encrypt(text.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token).decode()
    except InvalidToken as unreadable:
        raise EncryptionKeyError(
            f"A stored value cannot be decrypted with any key in {SETTING}. "
            "Was a key removed before running reencrypt_fields?"
        ) from unreadable
