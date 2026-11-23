"""System checks: problems Django reports at start-up (``manage.py check``)."""

from typing import Any

from django.conf import settings
from django.core.checks import Error, register

from apps.platform.core import encryption


@register()
def check_field_encryption_keys(app_configs: Any, **kwargs: Any) -> list[Error]:
    """The encryption keys must exist and be valid, or encrypted columns cannot be used."""
    return [
        Error(
            problem,
            hint='Make a key with: python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"',
            id="core.E001",
        )
        for problem in encryption.key_problems(list(settings.FIELD_ENCRYPTION_KEYS))
    ]
