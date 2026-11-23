"""Tests for comparable sales: past prices behind the fair-price explainer and bid checks."""

from datetime import date, timedelta
from typing import Any

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.inventory.catalog.models import ComparableSale
from apps.inventory.catalog.tests.helpers import (
    make_brand,
    make_category,
    make_product_model,
    make_sale,
)
from apps.platform.core.money import Money

pytestmark = pytest.mark.django_db


def messages(error: pytest.ExceptionInfo[ValidationError]) -> dict[str, list[str]]:
    return error.value.message_dict


def test_table_uses_the_data_model_name() -> None:
    assert ComparableSale._meta.db_table == "comparable_sales"


def test_sale_defaults_and_price() -> None:
    sale = make_sale(1_420_000)

    assert sale.currency == "USD"
    assert sale.product_model is None
    assert sale.department == ""
    assert sale.size_label == ""
    assert sale.source_url == ""
    assert sale.condition_grade == ""
    assert sale.price == Money(1_420_000)
    assert str(sale) == "Hermès, 14200.00 USD on 2026-10-01 (auction)"


def test_a_very_large_price_fits() -> None:
    """Prices are big integers: a $5 million watch is 500 million cents."""
    sale = make_sale(500_000_000_00)
    sale.refresh_from_db()

    assert sale.price_minor == 500_000_000_00


@pytest.mark.parametrize(
    "fields",
    [
        {"price_minor": 0},
        {"price_minor": -100},
        {"currency": "EUR"},
        {"source": "rumour"},
        {"department": "kids"},
    ],
)
def test_database_refuses_a_bad_sale(fields: dict[str, Any]) -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        make_sale(**fields)


def test_a_sale_in_the_future_is_refused() -> None:
    tomorrow = timezone.now().date() + timedelta(days=1)
    sale = ComparableSale(
        brand=make_brand(),
        category=make_category(),
        source="samwab",
        price_minor=100,
        sold_on=tomorrow,
    )

    with pytest.raises(ValidationError) as error:
        sale.full_clean()

    assert "sold_on" in messages(error)


def test_a_sale_today_is_fine() -> None:
    sale = ComparableSale(
        brand=make_brand(),
        category=make_category(),
        source="samwab",
        price_minor=100,
        sold_on=timezone.now().date(),
    )

    sale.full_clean()


def test_the_design_must_match_the_brand_and_category() -> None:
    kelly = make_product_model("Kelly 28")
    sale = ComparableSale(
        brand=make_brand("Chanel"),
        category=make_category("Watches"),
        product_model=kelly,
        source="auction",
        price_minor=100,
        sold_on=date(2026, 1, 1),
    )

    with pytest.raises(ValidationError) as error:
        sale.full_clean()

    assert set(messages(error)) == {"brand", "category"}


def test_a_sale_of_a_known_design() -> None:
    kelly = make_product_model("Kelly 28")

    sale = make_sale(product_model=kelly)
    sale.full_clean()

    assert (sale.brand, sale.category) == (kelly.brand, kelly.category)


def test_the_source_link_must_be_a_web_address() -> None:
    sale = ComparableSale(
        brand=make_brand(),
        category=make_category(),
        source="auction",
        price_minor=100,
        sold_on=date(2026, 1, 1),
        source_url="not a link",
    )

    with pytest.raises(ValidationError) as error:
        sale.full_clean()

    assert "source_url" in messages(error)


def test_a_brand_with_sales_cannot_be_deleted() -> None:
    from django.db.models import ProtectedError

    sale = make_sale()

    with pytest.raises(ProtectedError):
        sale.brand.delete()
