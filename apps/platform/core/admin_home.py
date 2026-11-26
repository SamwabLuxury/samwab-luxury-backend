"""The admin home page: the day's numbers and each person's task buttons (build E16).

``home`` is unfold's DASHBOARD_CALLBACK. It adds two things to the page:

- ``numbers``: pieces for sale now, paid orders, money taken this month, people on
  the mailing list. Everyone on staff sees them; they are counts, not records.
- ``tasks``: one button per job the person may do, so a new member of staff starts
  from "Add a new piece" rather than from a list of database tables. A button shows
  only if the person's role has the permission its screen needs.

Models are looked up by name so this platform module does not import shop apps.
"""

from typing import Any

from django.apps import apps
from django.db.models import Sum
from django.http import HttpRequest
from django.urls import reverse
from django.utils import timezone

from apps.platform.core.money import Money

# title, what it is for, icon, permission needed, admin page, extra query
TASKS: tuple[tuple[str, str, str, str, str, str], ...] = (
    (
        "Add a new piece",
        "Book in an item that has arrived.",
        "diamond",
        "pieces.add_piece",
        "admin:pieces_piece_add",
        "",
    ),
    (
        "Put a piece up for sale",
        "Set its price and publish it.",
        "sell",
        "listings.add_listing",
        "admin:listings_listing_add",
        "",
    ),
    (
        "Start a drop",
        "Plan a timed release of several pieces.",
        "event",
        "listings.add_drop",
        "admin:listings_drop_add",
        "",
    ),
    (
        "Record a past sale",
        "Save a sale elsewhere to guide our prices.",
        "query_stats",
        "catalog.add_comparablesale",
        "admin:catalog_comparablesale_add",
        "",
    ),
    (
        "Paid orders",
        "Orders that have been paid for.",
        "shopping_bag",
        "orders.view_order",
        "admin:orders_order_changelist",
        "?paid_at__isnull=False",
    ),
    (
        "Pieces for sale",
        "Everything live in the shop now.",
        "storefront",
        "listings.view_listing",
        "admin:listings_listing_changelist",
        "?status__exact=live",
    ),
    (
        "Mailing list",
        "People who asked to hear about drops.",
        "mail",
        "mailing_list.view_listmember",
        "admin:mailing_list_listmember_changelist",
        "?status__exact=confirmed",
    ),
)


def numbers() -> dict[str, int]:
    listing = apps.get_model("listings", "Listing")
    order = apps.get_model("orders", "Order")
    member = apps.get_model("mailing_list", "ListMember")
    now = timezone.localtime()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    paid = order.objects.filter(paid_at__isnull=False)
    return {
        "live_pieces": listing.objects.filter(status="live").count(),
        "paid_orders": paid.count(),
        "sales_this_month": paid.filter(paid_at__gte=month_start).aggregate(
            total=Sum("total_minor")
        )["total"]
        or 0,
        "list_members": member.objects.filter(status="confirmed").count(),
    }


def tasks_for(request: HttpRequest) -> list[dict[str, str]]:
    user = request.user
    return [
        {"title": title, "description": about, "icon": icon, "link": reverse(page) + query}
        for title, about, icon, perm, page, query in TASKS
        if user.has_perm(perm)
    ]


def home(request: HttpRequest, context: dict[str, Any]) -> dict[str, Any]:
    figures = numbers()
    context.update(
        {
            "numbers": figures,
            "sales_this_month_text": str(Money(figures["sales_this_month"])),
            "tasks": tasks_for(request),
        }
    )
    return context
