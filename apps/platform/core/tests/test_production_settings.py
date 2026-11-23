"""Tests for the production settings: Neon PostgreSQL, Render's address, static files, email."""

import importlib
from collections.abc import Callable, Iterator
from types import ModuleType

import pytest
from django.core.exceptions import ImproperlyConfigured

from configurations.settings import base

POOLED = "postgres://samwab:secret@ep-quiet-1-pooler.us-east-1.aws.neon.tech/samwab?sslmode=require"

Load = Callable[..., ModuleType]


@pytest.fixture
def load(monkeypatch: pytest.MonkeyPatch) -> Iterator[Load]:
    """Load the production settings with only the given environment variables set."""
    for name in (
        "DATABASE_URL",
        "RENDER_EXTERNAL_HOSTNAME",
        "DJANGO_ALLOWED_HOSTS",
        "DJANGO_CSRF_TRUSTED_ORIGINS",
        "DJANGO_EMAIL_TO_LOGS",
    ):
        monkeypatch.delenv(name, raising=False)

    monkeypatch.setenv("CLOUDINARY_URL", "cloudinary://123:made-up@samwab-test")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_settings_test")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_settings_test")

    def _load(**env: str) -> ModuleType:
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        module = importlib.import_module("configurations.settings.production")
        return importlib.reload(module)

    yield _load


# ---------- the database ----------


def test_the_database_is_neon_postgresql_from_database_url(load: Load) -> None:
    database = load(DATABASE_URL=POOLED).DATABASES["default"]

    assert database["ENGINE"] == "django.db.backends.postgresql"
    assert database["HOST"] == "ep-quiet-1-pooler.us-east-1.aws.neon.tech"
    assert database["NAME"] == "samwab"


def test_the_database_follows_neons_django_guide(load: Load) -> None:
    database = load(DATABASE_URL=POOLED).DATABASES["default"]

    # Neon's pooler (PgBouncer, transaction mode) cannot keep server-side cursors.
    assert database["DISABLE_SERVER_SIDE_CURSORS"] is True
    # Neon closes idle computes after 5 minutes: reuse connections for less, and check them.
    assert database["CONN_MAX_AGE"] == 300
    assert database["CONN_HEALTH_CHECKS"] is True


def test_the_database_connection_is_encrypted_even_without_sslmode(load: Load) -> None:
    database = load(DATABASE_URL=POOLED.split("?")[0]).DATABASES["default"]

    assert database["OPTIONS"]["sslmode"] == "require"


def test_a_stricter_sslmode_in_the_address_is_kept(load: Load) -> None:
    url = POOLED.replace("sslmode=require", "sslmode=verify-full")

    assert load(DATABASE_URL=url).DATABASES["default"]["OPTIONS"]["sslmode"] == "verify-full"


def test_production_refuses_to_start_without_a_database(load: Load) -> None:
    with pytest.raises(ImproperlyConfigured, match="DATABASE_URL"):
        load()


# ---------- the address ----------


def test_renders_address_is_allowed_and_trusted(load: Load) -> None:
    settings = load(DATABASE_URL=POOLED, RENDER_EXTERNAL_HOSTNAME="samwab-api.onrender.com")

    assert settings.ALLOWED_HOSTS == ["samwab-api.onrender.com"]
    assert settings.CSRF_TRUSTED_ORIGINS == ["https://samwab-api.onrender.com"]


def test_more_addresses_can_be_added(load: Load) -> None:
    settings = load(
        DATABASE_URL=POOLED,
        RENDER_EXTERNAL_HOSTNAME="samwab-api.onrender.com",
        DJANGO_ALLOWED_HOSTS="api.samwab.com",
        DJANGO_CSRF_TRUSTED_ORIGINS="https://samwab.com",
    )

    assert settings.ALLOWED_HOSTS == ["api.samwab.com", "samwab-api.onrender.com"]
    assert settings.CSRF_TRUSTED_ORIGINS == [
        "https://samwab.com",
        "https://samwab-api.onrender.com",
    ]


def test_without_any_address_nothing_is_allowed(load: Load) -> None:
    assert load(DATABASE_URL=POOLED).ALLOWED_HOSTS == []


# ---------- static files ----------


def test_whitenoise_serves_static_files_right_after_the_security_middleware() -> None:
    position = base.MIDDLEWARE.index("django.middleware.security.SecurityMiddleware")

    assert base.MIDDLEWARE[position + 1] == "whitenoise.middleware.WhiteNoiseMiddleware"
    assert str(base.STATIC_ROOT).endswith("staticfiles")


def test_production_serves_compressed_static_files_with_hashed_names(load: Load) -> None:
    storages = load(DATABASE_URL=POOLED).STORAGES

    assert storages["staticfiles"]["BACKEND"] == (
        "whitenoise.storage.CompressedManifestStaticFilesStorage"
    )
    assert storages["default"]["BACKEND"] == "apps.platform.core.storage.CloudinaryStorage"


# ---------- email ----------


def test_production_sends_email_by_smtp(load: Load) -> None:
    backend = load(DATABASE_URL=POOLED).MAILERS["default"]["BACKEND"]

    assert backend == "django.core.mail.backends.smtp.EmailBackend"


def test_until_an_email_service_exists_emails_can_go_to_the_logs(load: Load) -> None:
    mailer = load(DATABASE_URL=POOLED, DJANGO_EMAIL_TO_LOGS="true").MAILERS["default"]

    assert mailer == {"BACKEND": "django.core.mail.backends.console.EmailBackend"}


def test_only_the_deliberate_checks_are_switched_off(load: Load) -> None:
    assert load(DATABASE_URL=POOLED).SILENCED_SYSTEM_CHECKS == ["security.W021"]
    with_logs = load(DATABASE_URL=POOLED, DJANGO_EMAIL_TO_LOGS="true")
    assert with_logs.SILENCED_SYSTEM_CHECKS == ["security.W021", "mail.E001"]


# ---------- encrypted columns ----------


def test_production_refuses_to_start_without_encryption_keys(
    load: Load, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DJANGO_FIELD_ENCRYPTION_KEYS")

    with pytest.raises(ImproperlyConfigured, match="DJANGO_FIELD_ENCRYPTION_KEYS"):
        load(DATABASE_URL=POOLED)


def test_production_refuses_the_public_local_key(load: Load) -> None:
    from apps.platform.core.encryption import LOCAL_ONLY_ENCRYPTION_KEY

    with pytest.raises(ImproperlyConfigured, match="local-only"):
        load(DATABASE_URL=POOLED, DJANGO_FIELD_ENCRYPTION_KEYS=LOCAL_ONLY_ENCRYPTION_KEY)


def test_production_reads_its_own_keys(load: Load) -> None:
    from cryptography.fernet import Fernet

    new, old = Fernet.generate_key().decode(), Fernet.generate_key().decode()

    production = load(DATABASE_URL=POOLED, DJANGO_FIELD_ENCRYPTION_KEYS=f"{new},{old}")

    keys = production.FIELD_ENCRYPTION_KEYS
    assert keys == [new, old]


# ---------- payments ----------


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("STRIPE_SECRET_KEY", ""),
        ("STRIPE_SECRET_KEY", "pk_test_publishable_by_mistake"),
        ("STRIPE_WEBHOOK_SECRET", ""),
    ],
)
def test_production_refuses_to_start_without_stripe_keys(load: Load, name: str, value: str) -> None:
    with pytest.raises(ImproperlyConfigured, match="STRIPE_SECRET_KEY"):
        load(DATABASE_URL=POOLED, **{name: value})


def test_production_always_uses_stripe(load: Load) -> None:
    production = load(DATABASE_URL=POOLED, DJANGO_PAYMENT_PROVIDER="fake")

    provider = production.PAYMENT_PROVIDER
    assert provider == "stripe"


# ---------- photos ----------


def test_production_refuses_to_start_without_cloudinary(
    load: Load, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CLOUDINARY_URL")

    with pytest.raises(ImproperlyConfigured, match="CLOUDINARY_URL"):
        load(DATABASE_URL=POOLED)


def test_production_keeps_photos_on_cloudinary_in_the_live_folder(load: Load) -> None:
    production = load(DATABASE_URL=POOLED)

    storages = production.STORAGES
    folder = production.PHOTO_FOLDER
    assert storages["default"]["BACKEND"] == "apps.platform.core.storage.CloudinaryStorage"
    assert folder == "samwab/live"
