"""Shared test setup for every app."""

from pathlib import Path
from typing import Any

import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def _empty_cache() -> None:
    """allauth counts login and sign-up attempts in the cache. Start every test at zero."""
    cache.clear()


@pytest.fixture(autouse=True)
def _uploads_in_a_temporary_folder(settings: Any, tmp_path: Path) -> None:
    """Uploaded photos go to a folder deleted after each test, never into the project."""
    settings.MEDIA_ROOT = tmp_path / "media"
