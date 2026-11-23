"""Tests for the test settings: SQLite by default, PostgreSQL when CI says so."""

import importlib
from collections.abc import Iterator
from types import ModuleType

import pytest

import configurations.settings.test as test_settings


@pytest.fixture
def reload_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[ModuleType]:
    """Reload the test settings after the test has set its environment, then put them back."""
    yield test_settings
    monkeypatch.undo()
    importlib.reload(test_settings)


def test_tests_use_sqlite_by_default(
    monkeypatch: pytest.MonkeyPatch, reload_settings: ModuleType
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    database = importlib.reload(reload_settings).DATABASES["default"]

    assert database["ENGINE"] == "django.db.backends.sqlite3"


def test_ci_runs_the_tests_on_postgresql_through_database_url(
    monkeypatch: pytest.MonkeyPatch, reload_settings: ModuleType
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgres://samwab:secret@db.example:5433/samwab_test")

    database = importlib.reload(reload_settings).DATABASES["default"]

    assert database["ENGINE"] == "django.db.backends.postgresql"
    assert (database["NAME"], database["USER"], database["HOST"], database["PORT"]) == (
        "samwab_test",
        "samwab",
        "db.example",
        5433,
    )


def test_a_developers_machine_has_a_key_even_without_one_in_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import importlib

    from apps.platform.core.encryption import LOCAL_ONLY_ENCRYPTION_KEY
    from configurations.settings import base

    monkeypatch.setattr(base, "FIELD_ENCRYPTION_KEYS", [])
    local = importlib.reload(importlib.import_module("configurations.settings.local"))

    assert local.FIELD_ENCRYPTION_KEYS == [LOCAL_ONLY_ENCRYPTION_KEY]


def test_tests_keep_photos_in_a_folder_on_disk() -> None:
    from django.conf import settings

    assert settings.STORAGES["default"]["BACKEND"] == "django.core.files.storage.FileSystemStorage"


def test_a_cloudinary_url_switches_a_developers_machine_to_cloudinary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import importlib

    monkeypatch.setenv("CLOUDINARY_URL", "cloudinary://123:made-up@samwab-test")
    base = importlib.reload(importlib.import_module("configurations.settings.base"))
    try:
        storages = base.STORAGES
        folder = base.PHOTO_FOLDER
        assert storages["default"]["BACKEND"] == "apps.platform.core.storage.CloudinaryStorage"
        assert folder == "samwab/local"
    finally:
        monkeypatch.delenv("CLOUDINARY_URL")
        importlib.reload(base)
