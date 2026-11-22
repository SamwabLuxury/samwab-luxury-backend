"""Shared test setup for every app."""

import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def _empty_cache() -> None:
    """allauth counts login and sign-up attempts in the cache. Start every test at zero."""
    cache.clear()
