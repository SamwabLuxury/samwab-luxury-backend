"""Drops (D46, D51 #5: approved by the lead 25 Nov).

Staff build a drop in the admin: a number, a name, when it opens to everyone and
when it closes, and its lots (listings in order). Confirmed mailing-list members
see and can buy the lots ``DROP_EARLY_HOURS`` (24) hours before everyone else.
While a drop runs, its lots are on the drop's page, not in the normal shop. When
it closes, unsold lots appear in the normal shop by themselves: the rule is read
from the clock, so no job has to move anything.
"""

from datetime import timedelta
from typing import Any

import pytest
from django.core import mail
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import Client
from django.utils import timezone

from apps.platform.audit.models import AuditEvent
from apps.shop.listings import selectors, services
from apps.shop.listings.models import Drop, DropLot, Listing
from apps.shop.listings.tests.helpers import make_admin, make_listing, make_live_listing
from apps.shop.orders.tests.helpers import place_order
from apps.users.accounts.tests.helpers import admin_login
from apps.users.addresses.tests.helpers import make_address, make_user
from apps.users.mailing_list.models import ListMember

pytestmark = pytest.mark.django_db

DROPS = "/api/v1/drops/"
LISTINGS = "/api/v1/listings/"
NOW = timezone.now


def make_drop(phase: str, number: int = 7, **fields: Any) -> Drop:
    """A drop in one of its four phases, timed from the real clock."""
    now = NOW()
    public_at, closes_at = {
        "upcoming": (now + timedelta(hours=30), now + timedelta(hours=60)),
        "members": (now + timedelta(hours=2), now + timedelta(hours=50)),
        "open": (now - timedelta(hours=1), now + timedelta(hours=5)),
        "closed": (now - timedelta(hours=10), now - timedelta(hours=1)),
    }[phase]
    fields.setdefault("name", "The Winter Drop")
    return Drop.objects.create(number=number, public_at=public_at, closes_at=closes_at, **fields)


def lot(drop: Drop, listing: Listing | None = None, number: int = 1) -> Listing:
    listing = listing or make_live_listing()
    DropLot.objects.create(drop=drop, listing=listing, lot_number=number)
    return listing


def member(email: str = "ada@example.com") -> Any:
    ListMember.objects.get_or_create(
        email=email, defaults={"status": "confirmed", "confirmed_at": NOW()}
    )
    return make_user(email)


def logged_in(user: Any) -> Client:
    client = Client()
    client.force_login(user)
    return client


def shop_ids(client: Client) -> list[str]:
    return [row["id"] for row in client.get(LISTINGS).json()["results"]]


# ---------- the drop and its phases ----------


@pytest.mark.parametrize("phase", ["upcoming", "members", "open", "closed"])
def test_a_drop_knows_its_phase(phase: str) -> None:
    assert make_drop(phase).phase() == phase


def test_early_access_starts_24_hours_before_it_opens() -> None:
    drop = make_drop("open")

    assert drop.early_at == drop.public_at - timedelta(hours=24)


def test_a_drop_must_close_after_it_opens() -> None:
    now = NOW()
    drop = Drop(number=1, name="Bad", public_at=now, closes_at=now - timedelta(hours=1))

    with pytest.raises(ValidationError) as refused:
        drop.full_clean()

    assert "closes_at" in refused.value.message_dict


def test_the_database_keeps_drop_numbers_and_lots_unique() -> None:
    drop = make_drop("upcoming")
    listing = lot(drop)

    with pytest.raises(IntegrityError), transaction.atomic():
        make_drop("upcoming", number=7)
    with pytest.raises(IntegrityError), transaction.atomic():
        DropLot.objects.create(drop=make_drop("upcoming", number=8), listing=listing, lot_number=2)
    with pytest.raises(IntegrityError), transaction.atomic():
        DropLot.objects.create(drop=drop, listing=make_live_listing(), lot_number=1)
    with pytest.raises(IntegrityError), transaction.atomic():
        Drop.objects.filter(pk=drop.pk).update(closes_at=drop.public_at)


def test_only_an_open_listing_can_be_a_lot() -> None:
    listing = make_live_listing()
    services.withdraw_listing(listing, by=make_admin())

    with pytest.raises(ValidationError) as refused:
        DropLot(drop=make_drop("upcoming"), listing=listing, lot_number=1).full_clean()

    assert "listing" in refused.value.message_dict


def test_texts() -> None:
    drop = make_drop("open")
    listing = lot(drop)

    assert str(drop) == "Drop 7: The Winter Drop"
    assert str(listing.drop_lot) == f"Drop 7, lot 1: {listing}"


# ---------- who sees what ----------


@pytest.mark.parametrize("phase", ["upcoming", "members", "open"])
def test_a_running_drops_lots_stay_out_of_the_normal_shop(client: Client, phase: str) -> None:
    normal = make_live_listing()
    lot(make_drop(phase))

    assert shop_ids(client) == [str(normal.pk)]
    assert shop_ids(logged_in(member())) == [str(normal.pk)]


def test_after_it_closes_unsold_lots_join_the_normal_shop(client: Client) -> None:
    listing = lot(make_drop("closed"))

    assert shop_ids(client) == [str(listing.pk)]
    assert client.get(f"{LISTINGS}{listing.pk}/").status_code == 200


def test_before_early_access_nobody_sees_the_lots(client: Client) -> None:
    listing = lot(make_drop("upcoming"))

    assert client.get(f"{LISTINGS}{listing.pk}/").status_code == 404
    assert logged_in(member()).get(f"{LISTINGS}{listing.pk}/").status_code == 404
    assert logged_in(member()).get(f"{DROPS}7/").json()["lots"] == []


def test_in_the_early_hours_only_confirmed_members_see_the_lots(client: Client) -> None:
    listing = lot(make_drop("members"))
    pending = make_user("pending@example.com")
    ListMember.objects.create(email="pending@example.com", status="pending")

    assert client.get(f"{LISTINGS}{listing.pk}/").status_code == 404
    assert (
        logged_in(make_user("chidi@example.com")).get(f"{LISTINGS}{listing.pk}/").status_code == 404
    )
    assert logged_in(pending).get(f"{LISTINGS}{listing.pk}/").status_code == 404
    ada = logged_in(member())
    assert ada.get(f"{LISTINGS}{listing.pk}/").status_code == 200
    page = ada.get(f"{DROPS}7/").json()
    assert page["you_have_early_access"] is True
    assert [row["id"] for row in page["lots"]] == [str(listing.pk)]


def test_once_open_everyone_sees_the_lots_in_order(client: Client) -> None:
    drop = make_drop("open")
    second = lot(drop, number=2)
    first = lot(drop, number=1)

    page = client.get(f"{DROPS}7/").json()

    assert [row["id"] for row in page["lots"]] == [str(first.pk), str(second.pk)]
    assert [row["lot_number"] for row in page["lots"]] == [1, 2]
    assert page["you_have_early_access"] is False
    assert client.get(f"{LISTINGS}{first.pk}/").status_code == 200


def test_a_sold_or_withdrawn_lot_leaves_the_drop_page(client: Client) -> None:
    drop = make_drop("open")
    kept, gone = lot(drop, number=1), lot(drop, number=2)
    services.withdraw_listing(gone, by=make_admin())

    assert [row["id"] for row in client.get(f"{DROPS}7/").json()["lots"]] == [str(kept.pk)]


# ---------- the drops API ----------


def test_the_drops_list_shows_running_and_coming_drops_soonest_first(client: Client) -> None:
    make_drop("closed", number=1)
    make_drop("upcoming", number=3)
    open_drop = make_drop("open", number=2)
    lot(open_drop)

    rows = client.get(DROPS).json()["results"]

    assert [row["number"] for row in rows] == [2, 3]
    first = rows[0]
    assert first["name"] == "The Winter Drop"
    assert first["phase"] == "open"
    assert first["lot_count"] == 1
    for key in ("early_access_at", "opens_at", "closes_at", "description"):
        assert key in first


def test_a_drop_page_by_number(client: Client) -> None:
    make_drop("upcoming", description="Twelve pieces from one collection.")

    page = client.get(f"{DROPS}7/")

    assert page.status_code == 200
    assert page.json()["description"] == "Twelve pieces from one collection."
    assert page.json()["phase"] == "upcoming"
    assert client.get(f"{DROPS}99/").status_code == 404


def test_a_closed_drop_page_is_its_recap(client: Client) -> None:
    lot(make_drop("closed"))

    page = client.get(f"{DROPS}7/").json()

    assert page["phase"] == "closed"
    # Since E20 the recap lists every lot; an unsold one is also in the normal shop.
    assert [row["status"] for row in page["lots"]] == ["live"]


def test_the_drop_page_costs_a_fixed_number_of_queries(
    client: Client, django_assert_max_num_queries: Any
) -> None:
    drop = make_drop("open")
    for number in range(1, 6):
        lot(drop, number=number)

    with django_assert_max_num_queries(8):
        client.get(f"{DROPS}7/")


# ---------- buying and saving follow the same rule ----------


def test_nobody_can_buy_a_lot_before_early_access() -> None:
    listing = lot(make_drop("upcoming"))

    with pytest.raises(Exception) as refused:
        place_order(member(), listing)

    assert getattr(refused.value, "code", "") == "drop_not_open"


def test_in_the_early_hours_a_member_can_buy_and_others_cannot() -> None:
    listing = lot(make_drop("members"))

    with pytest.raises(Exception) as refused:
        place_order(make_user("chidi@example.com"), listing)
    order, _ = place_order(member(), listing)

    assert getattr(refused.value, "code", "") == "drop_not_open"
    assert order.listing_id == listing.pk


def test_the_api_refusal_is_plain(client: Client) -> None:
    listing = lot(make_drop("members"))
    chidi = make_user("chidi@example.com")
    client.force_login(chidi)

    response = client.post(
        "/api/v1/orders/",
        {
            "listing_id": str(listing.pk),
            "payment_option": "pay_in_full",
            "delivery_choice": "buyer_courier",
            "shipping_address_id": str(make_address(chidi).pk),
        },
        content_type="application/json",
        headers={"Idempotency-Key": "k1"},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "drop_not_open"


def test_once_open_anyone_can_buy() -> None:
    listing = lot(make_drop("open"))

    order, _ = place_order(make_user("chidi@example.com"), listing)

    assert order.listing_id == listing.pk


def test_a_member_can_save_a_lot_in_the_early_hours_and_others_cannot() -> None:
    listing = lot(make_drop("members"))

    services.save_listing(member(), listing.pk)
    with pytest.raises(Exception) as refused:
        services.save_listing(make_user("chidi@example.com"), listing.pk)

    assert getattr(refused.value, "code", "") == "not_found"
    assert [row.pk for row in selectors.saved_listings(make_user("ada@example.com"))] == [
        listing.pk
    ]


# ---------- the admin ----------


@pytest.fixture
def admin(client: Client) -> Client:
    admin_login(client, make_admin())
    return client


def drop_form(**fields: Any) -> dict[str, Any]:
    now = NOW()
    data = {
        "number": "12",
        "name": "Spring",
        "description": "",
        "public_at_0": (now + timedelta(days=3)).strftime("%Y-%m-%d"),
        "public_at_1": "10:00:00",
        "closes_at_0": (now + timedelta(days=5)).strftime("%Y-%m-%d"),
        "closes_at_1": "10:00:00",
        "lots-TOTAL_FORMS": "0",
        "lots-INITIAL_FORMS": "0",
    }
    return {**data, **fields}


def test_staff_create_a_drop_with_lots_and_it_is_audited(admin: Client) -> None:
    first, second = make_listing(), make_live_listing()

    response = admin.post(
        "/admin/listings/drop/add/",
        drop_form(
            **{
                "lots-TOTAL_FORMS": "2",
                "lots-0-listing": str(first.pk),
                "lots-0-lot_number": "1",
                "lots-1-listing": str(second.pk),
                "lots-1-lot_number": "2",
            }
        ),
    )

    assert response.status_code == 302, response.content.decode()[:3000]
    drop = Drop.objects.get(number=12)
    assert list(drop.lots.values_list("lot_number", flat=True)) == [1, 2]
    assert AuditEvent.objects.filter(action="listings.drop.created").count() == 1
    assert AuditEvent.objects.filter(action="listings.droplot.created").count() == 2


def test_lots_are_locked_once_early_access_has_started(admin: Client) -> None:
    drop = make_drop("members")
    lot(drop)

    page = admin.get(f"/admin/listings/drop/{drop.pk}/change/")

    assert page.status_code == 200
    assert 'name="lots-0-lot_number"' not in page.content.decode()


def test_staff_email_the_list_about_a_drop_once(admin: Client) -> None:
    drop = make_drop("upcoming")
    member("ada@example.com")
    member("bisi@example.com")
    ListMember.objects.create(email="left@example.com", status="unsubscribed")
    ListMember.objects.create(email="maybe@example.com", status="pending")

    admin.post(
        "/admin/listings/drop/",
        {"action": "email_the_list", "_selected_action": [str(drop.pk)]},
    )
    admin.post(
        "/admin/listings/drop/",
        {"action": "email_the_list", "_selected_action": [str(drop.pk)]},
    )

    assert sorted(m.to[0] for m in mail.outbox) == ["ada@example.com", "bisi@example.com"]
    message = mail.outbox[0]
    assert "The Winter Drop" in message.subject
    assert "/drops/7" in message.body
    assert "/mailing-list/unsubscribe/" in message.body  # each email has its own link
    drop.refresh_from_db()
    assert drop.announced_at is not None
    assert AuditEvent.objects.filter(action="listings.drop.announced").count() == 1


def test_the_drop_list_shows_each_drops_phase(admin: Client) -> None:
    make_drop("members")

    page = admin.get("/admin/listings/drop/").content.decode()

    assert "Drop 7" in page or "The Winter Drop" in page
    assert "members" in page


def test_an_email_that_fails_is_counted_and_the_others_still_go(
    admin: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    drop = make_drop("upcoming")
    member("ada@example.com")
    member("bisi@example.com")
    real_send = mail.send_mail

    def bisi_bounces(subject: str, body: str, sender: str, to: list[str], **kw: Any) -> int:
        if to == ["bisi@example.com"]:
            raise OSError("mailbox unavailable")
        return real_send(subject, body, sender, to, **kw)

    monkeypatch.setattr("apps.users.mailing_list.services.send_mail", bisi_bounces)

    sent, failed = services.announce_drop(drop, by=make_admin())

    assert (sent, failed) == (1, 1)
    assert [m.to for m in mail.outbox] == [["ada@example.com"]]
    event = AuditEvent.objects.get(action="listings.drop.announced")
    assert event.changes == {"sent": 1, "failed": 1}
