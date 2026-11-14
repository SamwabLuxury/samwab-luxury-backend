from rest_framework.pagination import CursorPagination as DRFCursorPagination


class CursorPagination(DRFCursorPagination):
    """The one way lists are paged in this API.

    The response has ``next`` and ``previous`` links and a ``results`` list.
    The front end follows the links; it never builds a page number itself.

    Why a cursor and not page numbers: page numbers skip or repeat rows when
    new rows arrive while someone is paging, and they get slow on large tables.

    Rows are ordered newest first. Our IDs are UUID version 7, which sort by
    creation time, so ordering by ``-id`` is both stable and fast.
    """

    ordering = "-id"
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100
