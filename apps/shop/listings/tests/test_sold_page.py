"""A sold piece keeps its page (build E19).

Figma: "Sold. The Speedy 30 has found a home." Until now a sold listing answered 404,
so a link shared before the sale, or the order confirmation, led nowhere.

- ``GET /api/v1/listings/{id}/`` answers a sold listing with ``status: "sold"`` and
  ``sold_at``; ``price_explainer`` is null (it is for deciding to buy).
- Nothing else changes: the shop list, the counts, saved pieces and drop pages still
  show pieces for sale only, and checkout still refuses a sold piece.
- Drafts and withdrawn listings stay 404, as does a piece later found not authentic.
- A sold lot follows its drop's rule: hidden from everyone but list members in the
  early hours, like the lot itself.
"""

from datetime import timedelta
from importlib import import_module
from typing import Any

import pytest
from django.apps import apps as global_apps
from django.utils import timezone
from rest_framework.test import APIClient

from apps.inventory.pieces.enums import VerificationStatus
from apps.shop.listings import services
from apps.shop.listings.enums import ListingStatus
from apps.shop.listings.models import DropLot, Listing
from apps.shop.listings.tests.helpers import make_live_listing, ready_piece
from apps.shop.listings.tests.test_drops import make_drop
from apps.shop.orders.models import Order
from apps.shop.orders.tests.helpers import address_of, place_order, stripe_says
from apps.users.addresses.tests.helpers import make_user
from apps.users.mailing_list.models import ListMember

pytestmark = pytest.mark.django_db


def page(listing: Listing, client: APIClient | None = None) -> Any:
    return (client or APIClient()).get(f"/api/v1/listings/{listing.pk}/")


def sold_listing() -> tuple[Listing, Order]:
    order, _ = place_order()
    stripe_says(order, "succeeded")
    order.refresh_from_db()
    listing = Listing.objects.get(pk=order.listing_id)
    return listing, order


def test_a_sold_piece_keeps_its_page() -> None:
    listing, _ = sold_listing()

    response = page(listing)

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["status"] == "sold"
    assert body["sold_at"] is not None
    assert body["price_explainer"] is None  # nothing to decide: it is not for sale
    assert body["reserved_until"] is None
    assert body["piece"]["title"]  # the page still shows the piece and its photos


def test_selling_records_when() -> None:
    before = timezone.now()
    listing, _ = sold_listing()

    assert listing.status == ListingStatus.SOLD
    assert listing.sold_at is not None
    assert before <= listing.sold_at <= timezone.now()


def test_a_live_piece_has_no_sold_time() -> None:
    body = page(make_live_listing()).json()

    assert body["status"] == "live"
    assert body["sold_at"] is None


def test_withdrawn_and_draft_listings_stay_hidden() -> None:
    listing = make_live_listing()
    services.withdraw_listing(listing, by=make_user("staff@samwab.com"))

    assert page(listing).status_code == 404


def test_a_sold_piece_found_not_authentic_disappears() -> None:
    listing, _ = sold_listing()
    listing.piece.verification_status = VerificationStatus.NOT_AUTHENTIC
    listing.piece.save(update_fields=["verification_status"])

    assert page(listing).status_code == 404


def test_a_sold_piece_is_not_for_sale_anywhere_else() -> None:
    listing, _ = sold_listing()
    client = APIClient()

    shop = client.get("/api/v1/listings/").json()
    facets = client.get("/api/v1/listings/facets/").json()

    assert str(listing.pk) not in [row["id"] for row in shop["results"]]
    assert shop["count"] == 0
    assert facets["total"] == 0


def test_checkout_still_refuses_a_sold_piece() -> None:
    listing, order = sold_listing()
    client = APIClient()
    client.force_authenticate(order.buyer)
    address = address_of(order.buyer).pk

    response = client.post(
        "/api/v1/orders/",
        {
            "listing_id": str(listing.pk),
            "payment_option": "pay_in_full",
            "delivery_choice": "buyer_courier",
            "shipping_address_id": str(address),
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="7f1c2b0e-0000-4000-8000-000000000001",
    )

    assert response.status_code == 409
    assert response.json()["code"] == "listing_unavailable"


def test_a_sold_lot_follows_its_drops_rule() -> None:
    drop = make_drop("members", number=5, name="Evening Edit")
    lot = make_live_listing(ready_piece())
    DropLot.objects.create(drop=drop, listing=lot, lot_number=1)
    services.mark_sold(lot)
    member = make_user("member@example.com")
    ListMember.objects.create(email=member.email, status="confirmed", confirmed_at=timezone.now())
    member_client = APIClient()
    member_client.force_authenticate(member)

    assert page(lot).status_code == 404  # early hours: list members only
    assert page(lot, member_client).status_code == 200


# ---------- the migration fills in the time for pieces already sold ----------


def backfill() -> None:
    migration = import_module("apps.shop.listings.migrations.0006_listing_sold_at")
    migration.fill_sold_at(global_apps, None)


def test_pieces_sold_before_this_build_get_their_payment_time() -> None:
    listing, order = sold_listing()
    paid_at = timezone.now() - timedelta(days=3)
    Order.objects.filter(pk=order.pk).update(paid_at=paid_at)
    Listing.objects.filter(pk=listing.pk).update(sold_at=None)

    backfill()

    listing.refresh_from_db()
    assert listing.sold_at == paid_at


def test_a_sold_piece_with_no_paid_order_falls_back_to_its_last_change() -> None:
    listing = make_live_listing()
    Listing.objects.filter(pk=listing.pk).update(status=ListingStatus.SOLD, sold_at=None)
    listing.refresh_from_db()

    backfill()

    listing.refresh_from_db()
    assert listing.sold_at == listing.updated_at


def test_the_backfill_leaves_other_listings_alone() -> None:
    live = make_live_listing()

    backfill()

    live.refresh_from_db()
    assert live.sold_at is None
