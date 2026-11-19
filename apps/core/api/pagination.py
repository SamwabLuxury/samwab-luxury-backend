from typing import Any
from urllib.parse import parse_qs, urlsplit

from rest_framework.pagination import CursorPagination as DRFCursorPagination


class CursorPagination(DRFCursorPagination):
    """The one way lists are paged in this API.

    The response has ``next`` and ``previous`` cursors and a ``results`` list.
    To get the next page, the front end sends the same request again with
    ``?cursor=<next>``. It never builds a page number itself.

    Why a cursor and not page numbers: page numbers skip or repeat rows when
    new rows arrive while someone is paging, and they get slow on large tables.

    Rows are ordered newest first. Our IDs are UUID version 7, which sort by
    creation time, so ordering by ``-id`` is both stable and fast.
    """

    ordering = "-id"
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100

    def _cursor_only(self, link: str | None) -> str | None:
        """DRF builds a full link. The API contract returns only the cursor."""
        if link is None:
            return None
        values = parse_qs(urlsplit(link).query).get(self.cursor_query_param)
        return values[0] if values else None

    def get_next_link(self) -> str | None:
        return self._cursor_only(super().get_next_link())

    def get_previous_link(self) -> str | None:
        return self._cursor_only(super().get_previous_link())

    def get_paginated_response_schema(self, schema: dict[str, Any]) -> dict[str, Any]:
        response_schema = super().get_paginated_response_schema(schema)
        for key in ("next", "previous"):
            response_schema["properties"][key] = {
                "type": "string",
                "nullable": True,
                "description": f"Send as ?cursor= to get the {key} page; null when there is none.",
            }
        return response_schema
