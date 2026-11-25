"""Who may see and buy a drop's lots, read from the clock (build E13).

One rule, used by the shop, the listing page, the drop page, saving and checkout:

- a listing in no drop, or in a closed drop: everyone (the normal shop);
- in a drop that has opened to everyone: everyone, on the drop's page;
- in its early hours: confirmed mailing-list members only;
- before that: nobody.
"""

from datetime import datetime, timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from apps.shop.listings.models import Listing
from apps.users.accounts.models import User
from apps.users.mailing_list.selectors import is_member


def has_early_access(viewer: User | None) -> bool:
    return bool(viewer is not None and viewer.is_authenticated and is_member(viewer.email))


def visible_to(viewer: User | None, *, now: datetime | None = None) -> Q:
    """The listings this person may see now (a filter on listings)."""
    now = now or timezone.now()
    allowed = (
        Q(drop_lot__isnull=True)
        | Q(drop_lot__drop__closes_at__lte=now)
        | Q(drop_lot__drop__public_at__lte=now)
    )
    if has_early_access(viewer):
        early = now + timedelta(hours=settings.DROP_EARLY_HOURS)
        allowed |= Q(drop_lot__drop__public_at__lte=early)
    return allowed


def in_normal_shop(*, now: datetime | None = None) -> Q:
    """Listings in no drop, or whose drop has closed."""
    now = now or timezone.now()
    return Q(drop_lot__isnull=True) | Q(drop_lot__drop__closes_at__lte=now)


def open_to(listing: Listing, viewer: User | None) -> bool:
    return Listing.objects.filter(visible_to(viewer), pk=listing.pk).exists()
