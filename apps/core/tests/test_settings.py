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
