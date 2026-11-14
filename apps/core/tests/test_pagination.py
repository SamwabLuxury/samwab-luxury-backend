"""Tests for apps/core/api/pagination.py.

Paging needs real rows, so these tests use a small table of their own.
It lives only in the throwaway test database, never in the real one.
"""

from collections.abc import Iterator
from typing import Any, ClassVar

import pytest
from django.db import connection, models
from django.test import Client
from django.urls import path
from rest_framework import serializers
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny

from apps.core.models import BaseModel

LIST_URL = "/api/v1/page-items/"
TOTAL = 130


class PageItem(BaseModel):
    """A model that exists only for these tests."""

    name = models.CharField(max_length=20)

    objects: ClassVar[models.Manager["PageItem"]] = models.Manager()

    class Meta:
        app_label = "core"

    def __str__(self) -> str:
        return self.name


class PageItemSerializer(serializers.ModelSerializer[PageItem]):
    class Meta:
        model = PageItem
        fields = ("id", "name")


class PageItemListView(ListAPIView[PageItem]):
    """Uses the project's default pagination: that is what these tests check."""

    queryset = PageItem.objects.all()
    serializer_class = PageItemSerializer
    authentication_classes = ()
    permission_classes = (AllowAny,)


urlpatterns = [path("api/v1/page-items/", PageItemListView.as_view())]

pytestmark = pytest.mark.urls(__name__)


@pytest.fixture
def items(transactional_db: None) -> Iterator[list[PageItem]]:
    """Fill the test table with 130 rows, oldest first.

    While the core app has no migrations, Django's test setup creates the table
    for us. Once core has migrations it will not, so we create it here if it is
    missing and remove it again afterwards.
    """
    created_here = PageItem._meta.db_table not in connection.introspection.table_names()
    if created_here:
        with connection.schema_editor() as editor:
            editor.create_model(PageItem)
    try:
        yield [PageItem.objects.create(name=f"item-{number:03d}") for number in range(TOTAL)]
    finally:
        if created_here:
            with connection.schema_editor() as editor:
                editor.delete_model(PageItem)


def names(page: dict[str, Any]) -> list[str]:
    return [row["name"] for row in page["results"]]


def test_first_page_has_25_rows_newest_first(client: Client, items: list[PageItem]) -> None:
    page = client.get(LIST_URL).json()

    assert names(page) == [f"item-{number:03d}" for number in range(129, 104, -1)]
    assert page["previous"] is None
    assert page["next"] is not None
    assert set(page) == {"next", "previous", "results"}


def test_following_next_visits_every_row_once_in_order(
    client: Client, items: list[PageItem]
) -> None:
    seen: list[str] = []
    url: str | None = LIST_URL
    pages = 0
    while url is not None:
        page = client.get(url).json()
        seen.extend(names(page))
        url = page["next"]
        pages += 1

    assert pages == 6  # 130 rows, 25 per page
    assert seen == [f"item-{number:03d}" for number in range(129, -1, -1)]


def test_previous_link_goes_back_to_the_first_page(client: Client, items: list[PageItem]) -> None:
    first = client.get(LIST_URL).json()
    second = client.get(first["next"]).json()

    back = client.get(second["previous"]).json()

    assert names(back) == names(first)


def test_page_size_can_be_chosen(client: Client, items: list[PageItem]) -> None:
    page = client.get(LIST_URL, {"page_size": 10}).json()

    assert len(page["results"]) == 10


def test_page_size_is_capped_at_100(client: Client, items: list[PageItem]) -> None:
    page = client.get(LIST_URL, {"page_size": 5000}).json()

    assert len(page["results"]) == 100


@pytest.mark.parametrize("bad_size", ["0", "-5", "abc", ""])
def test_a_bad_page_size_falls_back_to_25(
    client: Client, items: list[PageItem], bad_size: str
) -> None:
    page = client.get(LIST_URL, {"page_size": bad_size}).json()

    assert len(page["results"]) == 25


def test_new_rows_do_not_shift_the_pages_already_being_read(
    client: Client, items: list[PageItem]
) -> None:
    first = client.get(LIST_URL).json()
    PageItem.objects.create(name="brand-new")

    second = client.get(first["next"]).json()

    assert names(second) == [f"item-{number:03d}" for number in range(104, 79, -1)]
    assert "brand-new" not in names(second)


def test_a_broken_cursor_is_a_clean_404(client: Client, items: list[PageItem]) -> None:
    response = client.get(LIST_URL, {"cursor": "not-a-real-cursor"})

    assert response.status_code == 404
    assert response["Content-Type"] == "application/problem+json"
    assert response.json()["code"] == "not_found"


def test_an_empty_table_gives_an_empty_page(client: Client, items: list[PageItem]) -> None:
    PageItem.objects.all().delete()

    page = client.get(LIST_URL).json()

    assert page == {"next": None, "previous": None, "results": []}


def test_last_page_has_no_next_link(client: Client, items: list[PageItem]) -> None:
    PageItem.objects.exclude(name__in=["item-000", "item-001"]).delete()

    page = client.get(LIST_URL).json()

    assert names(page) == ["item-001", "item-000"]
    assert page["next"] is None
