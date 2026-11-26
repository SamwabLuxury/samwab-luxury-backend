"""The admin wears the shop's own colours from the Figma design (build E17).

Colours read from the design file's PDF export (24 Nov): espresso #2b1712 for
headings and buttons, cream #f7f2ea, sand #e8e0d2, lines #d9d0c1, gold #b08a4e,
body text #4f4e49, muted text #8c857a. The admin stays in the light look whatever
the computer's setting, as the design has no dark version.
"""

from typing import cast

import pytest
from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import Client

from apps.shop.listings.tests.helpers import make_admin, make_live_listing
from apps.users.accounts.tests.helpers import admin_login

ESPRESSO, CREAM, SAND, LINE, GOLD = "#2b1712", "#f7f2ea", "#e8e0d2", "#d9d0c1", "#b08a4e"


def test_the_admin_is_always_light_like_the_design() -> None:
    assert settings.UNFOLD["THEME"] == "light"


def test_the_colours_come_from_the_design() -> None:
    colours = cast("dict[str, dict[str, str]]", settings.UNFOLD["COLORS"])
    assert colours["primary"]["600"] == ESPRESSO  # buttons, the action bar, links
    assert colours["primary"]["500"] == GOLD
    assert colours["base"]["100"] == CREAM
    assert colours["base"]["200"] == SAND
    assert colours["base"]["300"] == LINE


def test_the_shop_stylesheet_exists_and_fixes_the_action_menu() -> None:
    path = finders.find("samwab_admin/samwab.css")
    assert path is not None
    css = open(path, encoding="utf-8").read()  # noqa: SIM115
    # The action menu's choices were white on grey: give them dark text on white.
    assert "#changelist-actions select option" in css
    assert ESPRESSO in css


@pytest.mark.django_db
def test_every_admin_page_loads_the_shop_look(client: Client) -> None:
    admin_login(client, make_admin())
    make_live_listing()

    page = client.get("/admin/listings/listing/").content.decode()

    assert "samwab_admin/samwab.css" in page
    assert "--color-base-100: rgb(247, 242, 234);" in page  # cream, as the theme writes it
    assert "--color-primary-600: rgb(43, 23, 18);" in page  # espresso
    assert "samwab_admin/monogram.svg" in page  # the S mark from the design


@pytest.mark.django_db
def test_the_pieces_section_has_its_own_name(client: Client) -> None:
    admin_login(client, make_admin())

    page = client.get("/admin/pieces/piece/").content.decode()

    assert ">Stock<" in page.replace("\n", "").replace(" ", "")
