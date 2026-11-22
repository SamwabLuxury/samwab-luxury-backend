"""Tests for the catalog tables: the rules the database and the admin enforce."""

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.db.models import ProtectedError

from apps.catalog.models import Brand, Category, Material, ProductModel
from apps.catalog.tests.helpers import make_brand, make_category, make_material, make_product_model

pytestmark = pytest.mark.django_db


def refuses(model: type[models.Model], **fields: object) -> None:
    """The database itself refuses this row, whatever code tries to save it."""
    with pytest.raises(IntegrityError), transaction.atomic():
        model._default_manager.create(**fields)


def messages(error: pytest.ExceptionInfo[ValidationError]) -> dict[str, list[str]]:
    return error.value.message_dict


# ---------- table names (from the team's data model) ----------


def test_tables_use_the_data_model_names() -> None:
    assert Brand._meta.db_table == "brands"
    assert Category._meta.db_table == "categories"
    assert ProductModel._meta.db_table == "product_models"
    assert Material._meta.db_table == "materials"


# ---------- brands ----------


def test_a_brand_is_active_by_default_and_shows_its_name() -> None:
    brand = make_brand("Hermès")

    assert brand.slug == "hermes"
    assert brand.is_active is True
    assert str(brand) == "Hermès"


def test_two_brands_cannot_share_a_slug() -> None:
    make_brand("Hermès", slug="hermes")

    refuses(Brand, name="Hermes Paris", slug="hermes")


def test_a_slug_must_be_lowercase() -> None:
    """Slugs go into web addresses. One spelling per brand keeps links stable."""
    refuses(Brand, name="Hermès", slug="Hermes")


def test_an_empty_slug_is_refused() -> None:
    refuses(Brand, name="Hermès", slug="")


def test_brand_form_rules() -> None:
    brand = Brand(name="", slug="not a slug!")

    with pytest.raises(ValidationError) as error:
        brand.full_clean()

    assert set(messages(error)) == {"name", "slug"}


def test_a_very_long_brand_name_is_refused() -> None:
    with pytest.raises(ValidationError) as error:
        Brand(name="x" * 121, slug="x").full_clean()

    assert "name" in messages(error)


def test_brand_names_in_any_language_are_kept_as_typed() -> None:
    brand = make_brand("Hermès", slug="hermes")
    brand.refresh_from_db()

    assert brand.name == "Hermès"


# ---------- categories ----------


def test_category_defaults() -> None:
    category = make_category("Bags")

    assert category.parent is None
    assert category.attribute_schema == {}
    assert category.flaw_types == []
    assert category.default_storage == "shelf"
    assert category.default_hs_code == ""
    assert category.sort_order == 0
    assert category.is_active is True
    assert category.updated_by is None
    assert str(category) == "Bags"


def test_a_category_can_sit_under_another() -> None:
    bags = make_category("Bags")
    top_handle = make_category("Top-handle bags", parent=bags)

    assert list(bags.children.all()) == [top_handle]
    assert str(top_handle) == "Bags / Top-handle bags"


def test_two_categories_cannot_share_a_slug() -> None:
    make_category("Bags", slug="bags")

    refuses(Category, name="Handbags", slug="bags")


def test_database_refuses_an_unknown_storage_kind() -> None:
    refuses(Category, name="Bags", slug="bags", default_storage="fridge")


def test_database_refuses_a_category_that_is_its_own_parent() -> None:
    bags = make_category("Bags")
    bags.parent_id = bags.id

    with pytest.raises(IntegrityError), transaction.atomic():
        bags.save()


def test_a_category_cannot_be_moved_under_its_own_child() -> None:
    """Otherwise the menu would loop forever: bags -> top-handle -> bags."""
    bags = make_category("Bags")
    top_handle = make_category("Top-handle bags", parent=bags)
    mini = make_category("Mini top-handle bags", parent=top_handle)

    bags.parent = mini
    with pytest.raises(ValidationError) as error:
        bags.full_clean()

    assert messages(error)["parent"] == ["A category cannot sit under itself or its own children."]


def test_a_category_cannot_be_its_own_parent_in_the_form() -> None:
    bags = make_category("Bags")
    bags.parent = bags

    with pytest.raises(ValidationError) as error:
        bags.full_clean()

    assert "parent" in messages(error)


def test_a_parent_in_use_cannot_be_deleted() -> None:
    """Staff retire a category instead of deleting it."""
    bags = make_category("Bags")
    make_category("Top-handle bags", parent=bags)

    with pytest.raises(ProtectedError):
        bags.delete()


@pytest.mark.parametrize(
    ("value", "valid"),
    [
        ({}, True),
        ({"type": "object", "properties": {"size_cm": {"type": "integer"}}}, True),
        ([], False),
        ("text", False),
        (None, False),
    ],
)
def test_attribute_schema_must_be_a_json_object(value: object, valid: bool) -> None:
    category = Category(name="Bags", slug="bags", attribute_schema=value)

    if valid:
        category.full_clean()
    else:
        with pytest.raises(ValidationError) as error:
            category.full_clean()
        assert "attribute_schema" in messages(error)


@pytest.mark.parametrize(
    ("value", "valid"),
    [
        ([], True),
        (["pilling", "missing_stone"], True),
        (["pilling", "pilling"], False),
        (["Pilling"], False),
        (["two words"], False),
        ([""], False),
        ([1], False),
        ({"pilling": True}, False),
    ],
)
def test_flaw_types_are_a_list_of_unique_codes(value: object, valid: bool) -> None:
    category = Category(name="Bags", slug="bags", flaw_types=value)

    if valid:
        category.full_clean()
    else:
        with pytest.raises(ValidationError) as error:
            category.full_clean()
        assert "flaw_types" in messages(error)


@pytest.mark.parametrize(
    ("value", "valid"),
    [
        ("", True),
        ("420221", True),
        ("4202210000", True),
        ("4202", False),
        ("42022100001", False),
        ("4202.21", False),
    ],
)
def test_hs_code_is_6_to_10_digits(value: str, valid: bool) -> None:
    category = Category(name="Bags", slug="bags", default_hs_code=value)

    if valid:
        category.full_clean()
    else:
        with pytest.raises(ValidationError) as error:
            category.full_clean()
        assert "default_hs_code" in messages(error)


# ---------- product models (named designs) ----------


def test_product_model_defaults() -> None:
    kelly = make_product_model("Kelly 28")

    assert kelly.slug == "kelly-28"
    assert kelly.department == ""
    assert kelly.era_from is None
    assert kelly.era_to is None
    assert kelly.attribute_schema == {}
    assert kelly.is_active is True
    assert str(kelly) == "Hermès Kelly 28"


def test_one_brand_cannot_have_two_designs_with_the_same_slug() -> None:
    hermes = make_brand("Hermès")
    bags = make_category("Bags")
    make_product_model("Kelly 28", brand=hermes, category=bags)

    refuses(ProductModel, name="Kelly 28 Sellier", slug="kelly-28", brand=hermes, category=bags)


def test_two_brands_can_use_the_same_design_slug() -> None:
    bags = make_category("Bags")
    make_product_model("Classic", brand=make_brand("Chanel"), category=bags)

    other = make_product_model("Classic", brand=make_brand("Dior"), category=bags)

    assert other.slug == "classic"


def test_database_refuses_an_unknown_department() -> None:
    refuses(
        ProductModel,
        name="Kelly 28",
        slug="kelly-28",
        brand=make_brand(),
        category=make_category(),
        department="kids",
    )


def test_database_refuses_an_era_that_ends_before_it_starts() -> None:
    refuses(
        ProductModel,
        name="Kelly 28",
        slug="kelly-28",
        brand=make_brand(),
        category=make_category(),
        era_from=2000,
        era_to=1990,
    )


@pytest.mark.parametrize(
    ("era_from", "era_to", "field"),
    [
        (2000, 1990, "era_to"),
        (1799, None, "era_from"),
        (None, 1799, "era_to"),
        (3000, None, "era_from"),
    ],
)
def test_era_years_must_make_sense(era_from: int | None, era_to: int | None, field: str) -> None:
    design = ProductModel(
        name="Kelly 28",
        slug="kelly-28",
        brand=make_brand(),
        category=make_category(),
        era_from=era_from,
        era_to=era_to,
    )

    with pytest.raises(ValidationError) as error:
        design.full_clean()

    assert field in messages(error)


def test_an_era_of_one_year_is_fine() -> None:
    design = ProductModel(
        name="Kelly 28",
        slug="kelly-28",
        brand=make_brand(),
        category=make_category(),
        era_from=1956,
        era_to=1956,
    )

    design.full_clean()


def test_a_brand_with_designs_cannot_be_deleted() -> None:
    kelly = make_product_model()

    with pytest.raises(ProtectedError):
        kelly.brand.delete()

    with pytest.raises(ProtectedError):
        kelly.category.delete()


# ---------- materials ----------


def test_material_defaults() -> None:
    togo = make_material("Togo leather")

    assert togo.is_exotic is False
    assert togo.domestic_only is False
    assert togo.cites_listed is False
    assert togo.sale_restricted is False
    assert togo.restriction_note == ""
    assert str(togo) == "Togo leather"


def test_material_names_are_unique_whatever_the_case() -> None:
    make_material("Gold")

    refuses(Material, name="gold")


@pytest.mark.parametrize("value", [[], "text", None])
def test_a_design_attribute_schema_must_be_a_json_object(value: object) -> None:
    design = ProductModel(
        name="Kelly 28",
        slug="kelly-28",
        brand=make_brand(),
        category=make_category(),
        attribute_schema=value,
    )

    with pytest.raises(ValidationError) as error:
        design.full_clean()

    assert "attribute_schema" in messages(error)


@pytest.mark.parametrize("model", ["category", "design"])
def test_an_attribute_schema_must_be_a_real_json_schema(model: str) -> None:
    """Pieces are checked against it, so a broken schema would refuse every piece."""
    broken = {"type": "banana"}
    if model == "category":
        row: models.Model = Category(name="Bags", slug="bags", attribute_schema=broken)
    else:
        row = ProductModel(
            name="Kelly 28",
            slug="kelly-28",
            brand=make_brand(),
            category=make_category(),
            attribute_schema=broken,
        )

    with pytest.raises(ValidationError) as error:
        row.full_clean()

    assert "is not valid under any of the given schemas" in messages(error)["attribute_schema"][0]
