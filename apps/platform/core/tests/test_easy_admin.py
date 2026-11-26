"""An admin site non-developers can use (build E16; the lead, 26 Nov).

Who uses it: staff listing pieces (intake staff), staff running drops and prices
(catalog editors), staff handling orders (support) and the owners checking numbers
(finance, view only). Each sees a home page with the day's numbers and the buttons
for their own tasks, and a menu grouped by task in plain words. The technical
tables (audit log, idempotency records, two-step records) stay for superusers.
The look comes from django-unfold 0.110.1 (MIT; Django 5.2 to 6.1).
"""

import re
from typing import Any

import pytest
from django.contrib import admin
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from unfold.admin import ModelAdmin as UnfoldModelAdmin
from unfold.admin import StackedInline, TabularInline
from unfold.sites import UnfoldAdminSite

from apps.shop.listings.models import Listing
from apps.shop.listings.tests.helpers import make_live_listing
from apps.shop.orders.models import Order
from apps.shop.orders.tests.helpers import place_order
from apps.users.accounts import roles
from apps.users.accounts.tests.helpers import admin_login, make_staff
from apps.users.mailing_list.models import ListMember

pytestmark = pytest.mark.django_db


def test_the_admin_uses_the_new_look() -> None:
    assert isinstance(admin.site, UnfoldAdminSite)


def test_every_screen_uses_the_new_look() -> None:
    for model, model_admin in admin.site._registry.items():
        if model._meta.app_label in ("auth", "mfa", "account", "usersessions"):
            continue  # third-party screens we leave to their own apps or hide
        assert isinstance(model_admin, UnfoldModelAdmin), model
        for inline in model_admin.inlines:
            assert issubclass(inline, (TabularInline, StackedInline)), inline


def logged_in(*role_names: str, email: str = "staff@samwab.com") -> Client:
    client = Client()
    admin_login(client, make_staff(email, *role_names))
    return client


@pytest.fixture
def superuser_client(client: Client) -> Client:
    from apps.shop.listings.tests.helpers import make_admin

    admin_login(client, make_admin())
    return client


def test_every_list_and_add_page_opens_for_a_superuser(superuser_client: Client) -> None:
    make_live_listing()
    for model, model_admin in admin.site._registry.items():
        info = (model._meta.app_label, model._meta.model_name)
        page = superuser_client.get(reverse("admin:{}_{}_changelist".format(*info)))
        assert page.status_code == 200, (info, page.status_code)
        if model_admin.has_add_permission(_request(superuser_client)):
            add = superuser_client.get(reverse("admin:{}_{}_add".format(*info)))
            assert add.status_code == 200, (info, add.status_code)


def _request(client: Client) -> Any:
    from django.test import RequestFactory

    from apps.users.accounts.models import User

    request = RequestFactory().get("/admin/")
    request.user = User.objects.get(pk=client.session["_auth_user_id"])
    return request


# ---------- the home page ----------


def test_the_home_page_shows_the_days_numbers(superuser_client: Client) -> None:
    make_live_listing()
    order, _ = place_order()
    # Stand in for the payment webhook: the order is paid and its piece is sold.
    Order.objects.filter(pk=order.pk).update(status="paid", paid_at=timezone.now())
    Listing.objects.filter(pk=order.listing_id).update(status="sold")
    ListMember.objects.create(email="a@example.com", status="confirmed")
    ListMember.objects.create(email="b@example.com", status="pending")

    page = superuser_client.get("/admin/")

    text = page.content.decode()
    assert page.status_code == 200
    numbers = page.context["numbers"]
    assert numbers["live_pieces"] == 1  # one listing was bought, so it is no longer live
    assert numbers["paid_orders"] == 1
    assert numbers["sales_this_month"] == order.total_minor
    assert numbers["list_members"] == 1
    assert "Pieces for sale" in text
    assert "Paid orders" in text
    assert "Mailing list" in text


def test_each_person_sees_the_buttons_for_their_own_tasks() -> None:
    lister = logged_in(roles.INTAKE_STAFF, email="lister@samwab.com").get("/admin/")
    drops = logged_in(roles.CATALOG_EDITOR, email="drops@samwab.com").get("/admin/")
    orders = logged_in(roles.SUPPORT, email="orders@samwab.com").get("/admin/")
    owner = logged_in(roles.FINANCE, email="owner@samwab.com").get("/admin/")

    tasks = {
        "lister": [t["title"] for t in lister.context["tasks"]],
        "drops": [t["title"] for t in drops.context["tasks"]],
        "orders": [t["title"] for t in orders.context["tasks"]],
        "owner": [t["title"] for t in owner.context["tasks"]],
    }
    assert "Add a new piece" in tasks["lister"]
    assert "Put a piece up for sale" in tasks["lister"]
    assert "Start a drop" not in tasks["lister"]
    assert "Start a drop" in tasks["drops"]
    assert "Record a past sale" in tasks["drops"]
    assert "Paid orders" in tasks["orders"]
    assert "Add a new piece" not in tasks["orders"]
    assert tasks["owner"] == ["Paid orders", "Pieces for sale", "Mailing list"]


# ---------- who may open what ----------


@pytest.mark.parametrize(
    ("role", "allowed", "refused"),
    [
        (
            roles.INTAKE_STAFF,
            ["pieces/piece", "listings/listing", "catalog/brand"],
            ["orders/order", "listings/drop", "audit/auditevent"],
        ),
        (
            roles.CATALOG_EDITOR,
            [
                "listings/drop",
                "catalog/comparablesale",
                "listings/listing",
                "mailing_list/listmember",
            ],
            ["orders/order", "audit/auditevent"],
        ),
        (
            roles.SUPPORT,
            ["orders/order", "listings/listing", "mailing_list/listmember"],
            ["pieces/piece", "audit/auditevent", "listings/drop"],
        ),
        (
            roles.FINANCE,
            ["orders/order", "listings/listing", "mailing_list/listmember", "listings/drop"],
            ["audit/auditevent", "idempotency/idempotencykey"],
        ),
    ],
)
def test_each_role_opens_only_its_own_screens(
    role: str, allowed: list[str], refused: list[str]
) -> None:
    client = logged_in(role)

    for path in allowed:
        assert client.get(f"/admin/{path}/").status_code == 200, (role, path)
    for path in refused:
        assert client.get(f"/admin/{path}/").status_code == 403, (role, path)


def test_the_owners_can_look_but_not_change() -> None:
    client = logged_in(roles.FINANCE)
    listing = make_live_listing()

    page = client.get(f"/admin/listings/listing/{listing.pk}/change/")

    assert page.status_code == 200
    assert page.context["has_change_permission"] is False
    assert client.get("/admin/listings/listing/add/").status_code == 403


def test_intake_staff_can_put_a_piece_up_for_sale() -> None:
    client = logged_in(roles.INTAKE_STAFF)

    assert client.get("/admin/listings/listing/add/").status_code == 200


# ---------- the menu ----------


def test_the_menu_is_grouped_by_task_in_plain_words(superuser_client: Client) -> None:
    from apps.platform.core.admin_menu import NAVIGATION

    groups = [group["title"] for group in NAVIGATION]

    assert groups == [
        "Shop",
        "Drops and mailing list",
        "Orders",
        "Catalog and prices",
        "People",
        "Technical",
    ]


def test_a_role_sees_only_its_menu_items() -> None:
    client = logged_in(roles.SUPPORT)

    text = client.get("/admin/").content.decode()

    assert "Orders" in text
    assert "Audit log" not in text
    assert "Add a new piece" not in text


def test_the_technical_tables_are_for_superusers_only(superuser_client: Client) -> None:
    text = superuser_client.get("/admin/").content.decode()

    assert "Audit log" in text


def test_every_action_says_which_permission_it_needs() -> None:
    """Django offers an action with no stated permission to anyone who can open the
    list, so a view-only role could otherwise publish, withdraw or retire."""
    for model, model_admin in admin.site._registry.items():
        if not model.__module__.startswith("apps."):
            continue  # allauth's login-email screen is for superusers only
        for action in model_admin.actions or ():
            func = action if callable(action) else getattr(model_admin, action)
            assert getattr(func, "allowed_permissions", None), (model, func.__name__)


def test_a_view_only_role_is_offered_no_actions() -> None:
    from apps.shop.listings.tests.helpers import make_listing

    make_listing()
    client = logged_in(roles.FINANCE)

    page = client.get("/admin/listings/listing/")

    assert page.status_code == 200
    assert page.context["action_form"] is None or not page.context["cl"].actions


def test_intake_staff_cannot_retire_a_brand() -> None:
    from apps.inventory.catalog.tests.helpers import make_brand

    brand = make_brand("Hermès")
    client = logged_in(roles.INTAKE_STAFF)

    client.post(
        "/admin/catalog/brand/",
        {"action": "retire_selected", "_selected_action": [str(brand.pk)]},
    )

    brand.refresh_from_db()
    assert brand.is_active


# ---------- plain names on every page ----------


def title_of(page: str) -> str:
    found = re.search(r"<title>(.*?)</title>", page, re.S)
    return " ".join(found.group(1).split()) if found else ""


@pytest.mark.parametrize(
    ("path", "name"),
    [
        ("/admin/listings/listing/", "Pieces for sale"),
        ("/admin/catalog/comparablesale/", "Past sales"),
        ("/admin/catalog/captureprotocol/", "Photo checklists"),
        ("/admin/mailing_list/listmember/", "Mailing list members"),
        ("/admin/accounts/user/", "Accounts"),
    ],
)
def test_pages_are_named_as_staff_say_them(superuser_client: Client, path: str, name: str) -> None:
    page = superuser_client.get(path).content.decode()

    # Django's own title is "Select listing to change"; staff see the plain name.
    assert title_of(page) == f"{name} | Samwab admin"


def test_the_home_page_is_called_home(superuser_client: Client) -> None:
    page = superuser_client.get("/admin/").content.decode()

    assert "Site administration" not in page
    assert title_of(page) == "Home | Samwab admin"


def test_the_shop_screens_sit_under_plain_section_names(superuser_client: Client) -> None:
    page = superuser_client.get("/admin/listings/listing/").content.decode()

    assert ">Shop<" in page.replace("\n", "").replace("  ", "")


def test_the_add_page_names_the_thing_plainly(superuser_client: Client) -> None:
    page = superuser_client.get("/admin/listings/listing/add/").content.decode()

    assert title_of(page) == "Add piece for sale | Samwab admin"
