"""Settings for automated tests (pytest and CI)."""

import os

# Tests must not depend on a developer's .env file.
os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-key-never-used-outside-tests")

from .base import *

# Fast hashing keeps tests quick. Never use this outside tests.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
