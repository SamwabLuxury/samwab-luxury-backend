"""Settings for automated tests (pytest and CI)."""

import os

# Tests must not depend on a developer's .env file.
os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-key-never-used-outside-tests")

from .base import *
from .base import env

# CI also runs every test on PostgreSQL, the production database, by setting
# DATABASE_URL (for example postgres://user:password@localhost:5432/samwab).
# Without it, tests use SQLite as on your own machine.
if "DATABASE_URL" in os.environ:
    DATABASES = {"default": env.db("DATABASE_URL")}

# Tests never run collectstatic; skip WhiteNoise's start-up scan (WhiteNoise docs).
WHITENOISE_AUTOREFRESH = True

# Fast hashing keeps tests quick. Never use this outside tests.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
