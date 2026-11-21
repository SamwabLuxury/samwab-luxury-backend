"""The catalog: what can be sold on Samwab.

Staff run these tables in the admin site (the catalog manager). The public
API only reads them. Brands, categories and designs are never deleted:
staff retire them (``is_active = False``), and their pieces and history stay.
"""

import re
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone

from apps.catalog.enums import Department, Storage
from apps.core.models import BaseModel

FLAW_CODE = re.compile(r"^[a-z][a-z0-9_]*$")
FIRST_ERA_YEAR = 1800
hs_code_validator = RegexValidator(r"^\d{6,10}$", "Use 6 to 10 digits, with no dots or spaces.")


def lowercase_slug(name: str) -> models.CheckConstraint:
    """Slugs go into web addresses, so each one has exactly one spelling."""
    return models.CheckConstraint(
        condition=models.Q(slug=Lower("slug")) & ~models.Q(slug=""), name=name
    )


SCHEMA_MESSAGE = 'Use a JSON object, such as {} or {"type": "object"}.'


class Brand(BaseModel):
    """A maison, such as Hermès or Rolex."""

    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=120, unique=True, help_text="Used in web addresses.")
    is_active = models.BooleanField(default=True, help_text="Untick to retire the brand.")

    class Meta:
        db_table = "brands"
        ordering = ("slug",)
        constraints = (lowercase_slug("brands_slug_is_lowercase"),)

    def __str__(self) -> str:
        return self.name


class Category(BaseModel):
    """A kind of piece, such as Bags or Watches. Categories can sit under one another."""

    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="children"
    )
    name = models.CharField(max_length=80)
    slug = models.SlugField(max_length=80, unique=True, help_text="Used in web addresses.")
    attribute_schema = models.JSONField(
        default=dict,
        blank=True,
        help_text="JSON Schema every piece in the category must pass.",
    )
    flaw_types = models.JSONField(
        default=list,
        blank=True,
        help_text='Flaw codes a grader can record, such as ["pilling", "missing_stone"].',
    )
    default_storage = models.CharField(
        max_length=20, choices=Storage.choices, default=Storage.SHELF
    )
    default_hs_code = models.CharField(
        max_length=10,
        blank=True,
        validators=[hs_code_validator],
        help_text="Customs tariff code for the commercial invoice.",
    )
    sort_order = models.PositiveSmallIntegerField(
        default=0, help_text="Lower numbers come first in menus and browse pages."
    )
    is_active = models.BooleanField(
        default=True, help_text="Untick to retire it. Its pieces keep it; it takes no new listings."
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        editable=False,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="The staff member who last changed it.",
    )

    class Meta:
        db_table = "categories"
        ordering = ("sort_order", "slug")
        verbose_name_plural = "categories"
        constraints = (
            lowercase_slug("categories_slug_is_lowercase"),
            models.CheckConstraint(
                condition=models.Q(default_storage__in=Storage.values),
                name="categories_default_storage_is_known",
            ),
            models.CheckConstraint(
                condition=~models.Q(parent=models.F("id")),
                name="categories_not_own_parent",
            ),
        )

    def __str__(self) -> str:
        return f"{self.parent.name} / {self.name}" if self.parent else self.name

    def clean(self) -> None:
        errors: dict[str, str] = {}
        if not isinstance(self.attribute_schema, dict):
            errors["attribute_schema"] = SCHEMA_MESSAGE
        if self.parent_id is not None and self.parent_id in self._self_and_descendant_ids():
            errors["parent"] = "A category cannot sit under itself or its own children."
        if not self._flaw_types_are_valid():
            errors["flaw_types"] = (
                'Use a list of unique codes in lowercase, such as ["pilling", "missing_stone"].'
            )
        if errors:
            raise ValidationError(errors)

    def _self_and_descendant_ids(self) -> set[Any]:
        found = {self.id}
        layer = {self.id}
        while layer:
            layer = set(
                Category.objects.filter(parent_id__in=layer)
                .exclude(id__in=found)
                .values_list("id", flat=True)
            )
            found |= layer
        return found

    def _flaw_types_are_valid(self) -> bool:
        codes = self.flaw_types
        return (
            isinstance(codes, list)
            and all(isinstance(code, str) and FLAW_CODE.match(code) for code in codes)
            and len(set(codes)) == len(codes)
        )


class ProductModel(BaseModel):
    """A named design, such as the Kelly 28, the Love bracelet or the Bar jacket."""

    brand = models.ForeignKey(Brand, on_delete=models.PROTECT, related_name="product_models")
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="product_models")
    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=160, help_text="Used in web addresses. Unique per brand.")
    department = models.CharField(
        max_length=10,
        choices=Department.choices,
        blank=True,
        help_text="Who it is made for. Its pieces start with this value.",
    )
    era_from = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="First production year."
    )
    era_to = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Last production year. Leave empty if still made."
    )
    attribute_schema = models.JSONField(
        default=dict,
        blank=True,
        help_text="Extra JSON Schema rules for this design, on top of its category's.",
    )
    is_active = models.BooleanField(default=True, help_text="Untick to retire the design.")

    class Meta:
        db_table = "product_models"
        ordering = ("slug",)
        verbose_name = "design"
        constraints = (
            models.UniqueConstraint(fields=("brand", "slug"), name="product_models_brand_slug"),
            lowercase_slug("product_models_slug_is_lowercase"),
            models.CheckConstraint(
                condition=models.Q(department__in=[*Department.values, ""]),
                name="product_models_department_is_known",
            ),
            models.CheckConstraint(
                condition=models.Q(era_from__isnull=True)
                | models.Q(era_to__isnull=True)
                | models.Q(era_from__lte=models.F("era_to")),
                name="product_models_era_in_order",
            ),
        )

    def __str__(self) -> str:
        return f"{self.brand.name} {self.name}"

    def clean(self) -> None:
        latest = timezone.now().year + 1
        errors: dict[str, str] = {}
        if not isinstance(self.attribute_schema, dict):
            errors["attribute_schema"] = SCHEMA_MESSAGE
        for field in ("era_from", "era_to"):
            year = getattr(self, field)
            if year is not None and not FIRST_ERA_YEAR <= year <= latest:
                errors[field] = f"Use a year from {FIRST_ERA_YEAR} to {latest}."
        if (
            not errors
            and self.era_from is not None
            and self.era_to is not None
            and self.era_to < self.era_from
        ):
            errors["era_to"] = "The last year cannot be before the first year."
        if errors:
            raise ValidationError(errors)


class Material(BaseModel):
    """What a piece is made of, with the rules some materials carry for selling and shipping."""

    name = models.CharField(max_length=80)
    is_exotic = models.BooleanField(default=False, help_text="An exotic skin, such as crocodile.")
    domestic_only = models.BooleanField(
        default=False,
        help_text="Sold only to buyers in the piece's home country (export needs permits).",
    )
    cites_listed = models.BooleanField(
        default=False, help_text="On the CITES list. Blocks international delivery."
    )
    sale_restricted = models.BooleanField(
        default=False,
        help_text="Fur, ivory, tortoiseshell, coral: staff review before listing.",
    )
    restriction_note = models.TextField(blank=True)

    class Meta:
        db_table = "materials"
        ordering = ("name",)
        constraints = (models.UniqueConstraint(Lower("name"), name="materials_name_unique"),)

    def __str__(self) -> str:
        return self.name
