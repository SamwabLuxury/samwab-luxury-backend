"""Order numbers: ``YYMM-NNNN``, such as 2611-0042 (D46, D51).

Year and month (UTC), then a count that starts at 0001 every month. After 9999 the
count grows to five digits (2611-10000) rather than failing.

``next_order_number`` must run inside the transaction that saves the order: the
month's counter row stays locked until that transaction ends, so concurrent
checkouts wait their turn, and a checkout that is rolled back (Stripe unreachable)
gives its number back.
"""

from datetime import UTC, datetime

from django.db.models import F

from apps.shop.orders.models import OrderNumberCounter


def next_order_number(at: datetime) -> str:
    month = at.astimezone(UTC).strftime("%y%m")
    # The first order of a month creates the row; if two arrive together, one insert
    # is ignored instead of failing.
    OrderNumberCounter.objects.bulk_create(
        [OrderNumberCounter(month=month, last=0)], ignore_conflicts=True
    )
    # UPDATE locks the row until the transaction ends: the next checkout waits here.
    OrderNumberCounter.objects.filter(month=month).update(last=F("last") + 1)
    last = OrderNumberCounter.objects.values_list("last", flat=True).get(month=month)
    return f"{month}-{last:04d}"
