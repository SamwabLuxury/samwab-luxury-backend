"""A piece: one physical object that Samwab holds, sells or has checked.

Three columns are projections of other records, not the truth:

- ``verification_status`` comes from the latest authentication check (build 28).
- ``custody_status`` comes from custody events (build 16).
- ``current_owner`` comes from the ownership ledger (build 17).

Until those builds exist, staff set the owner when they register a piece, and
the statuses change only through ``services.move_custody`` and
``services.set_verification``, which follow the moves in ``state.py``.
``current_location`` (a vault shelf) arrives with build 16.
"""

from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models.functions import Length, Upper
from django.db.models.lookups import Exact
from django.utils import timezone

from apps.inventory.catalog.enums import Department
from apps.inventory.catalog.models import Brand, Category, Material, ProductModel
from apps.inventory.catalog.models.catalog import FIRST_ERA_YEAR, hs_code_validator
from apps.inventory.pieces.enums import (
    AuthenticationBasis,
    ConditionGrade,
    CustodyStatus,
    SizeSystem,
    Source,
    VerificationStatus,
)
from apps.platform.core.json_schema import attribute_errors
from apps.platform.core.models import BaseModel
from apps.platform.core.money import DEFAULT_CURRENCY

country_validator = RegexValidator(r"^[A-Z]{2}$", "Use the two-letter country code, such as US.")


def known(field: str, choices: type[models.TextChoices], *, blank: bool = False) -> models.Q:
    values = [*choices.values, ""] if blank else choices.values
    return models.Q(**{f"{field}__in": values})


class Piece(BaseModel):
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="pieces")
    brand = models.ForeignKey(Brand, on_delete=models.PROTECT, related_name="pieces")
    product_model = models.ForeignKey(
        ProductModel,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="pieces",
        verbose_name="design",
        help_text="Empty until identified, or when there is no named design.",
    )
    department = models.CharField(
        max_length=10,
        choices=Department.choices,
        blank=True,
        help_text="Leave empty to take the design's department.",
    )
    size_system = models.CharField(max_length=10, choices=SizeSystem.choices, blank=True)
    size_label = models.CharField(max_length=20, blank=True, help_text="Such as 38, M or 7.5.")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    production_year = models.PositiveSmallIntegerField(null=True, blank=True)
    attributes = models.JSONField(
        default=dict,
        blank=True,
        help_text="Measurements, metal, stones, hardware. Checked against the category's "
        "and the design's schemas.",
    )
    hs_code = models.CharField(
        max_length=10,
        blank=True,
        validators=[hs_code_validator],
        help_text="Leave empty to take the category's code.",
    )
    serial_or_date_code = models.CharField(
        max_length=40, blank=True, help_text="Staff only. Never shown to the public."
    )
    source = models.CharField(max_length=20, choices=Source.choices)
    home_country = models.CharField(
        max_length=2,
        validators=[country_validator],
        help_text="Where the piece is held. Pieces with a domestic-only material sell only "
        "to buyers delivering here.",
    )
    authentication_basis = models.CharField(
        max_length=30, choices=AuthenticationBasis.choices, blank=True
    )
    acquisition_cost_minor = models.PositiveBigIntegerField(
        null=True, blank=True, help_text="House stock only. US cents."
    )
    currency = models.CharField(max_length=3, default=DEFAULT_CURRENCY, editable=False)
    condition_grade = models.CharField(max_length=20, choices=ConditionGrade.choices, blank=True)
    verification_status = models.CharField(
        max_length=20,
        choices=VerificationStatus.choices,
        default=VerificationStatus.UNVERIFIED,
        editable=False,
    )
    custody_status = models.CharField(
        max_length=20,
        choices=CustodyStatus.choices,
        default=CustodyStatus.WITH_OWNER,
        editable=False,
    )
    current_owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="pieces"
    )
    storage_free_until = models.DateTimeField(null=True, blank=True)
    materials = models.ManyToManyField(
        Material, through="PieceMaterial", blank=True, related_name="pieces"
    )

    class Meta:
        db_table = "pieces"
        ordering = ("-id",)
        indexes = (
            models.Index(fields=("category", "department", "size_label"), name="pieces_browse_idx"),
        )
        constraints = (
            models.CheckConstraint(
                condition=known("department", Department), name="pieces_department_is_known"
            ),
            models.CheckConstraint(
                condition=known("size_system", SizeSystem, blank=True),
                name="pieces_size_system_is_known",
            ),
            models.CheckConstraint(
                condition=known("source", Source), name="pieces_source_is_known"
            ),
            models.CheckConstraint(
                condition=known("authentication_basis", AuthenticationBasis, blank=True),
                name="pieces_authentication_basis_is_known",
            ),
            models.CheckConstraint(
                condition=known("condition_grade", ConditionGrade, blank=True),
                name="pieces_condition_grade_is_known",
            ),
            models.CheckConstraint(
                condition=known("verification_status", VerificationStatus),
                name="pieces_verification_status_is_known",
            ),
            models.CheckConstraint(
                condition=known("custody_status", CustodyStatus),
                name="pieces_custody_status_is_known",
            ),
            models.CheckConstraint(
                condition=models.Q(currency=DEFAULT_CURRENCY), name="pieces_in_usd"
            ),
            models.CheckConstraint(
                condition=models.Q(home_country=Upper("home_country"))
                & models.Q(Exact(Length("home_country"), 2)),
                name="pieces_home_country_is_a_code",
            ),
            models.CheckConstraint(
                condition=models.Q(source=Source.HOUSE_STOCK)
                | models.Q(acquisition_cost_minor__isnull=True),
                name="pieces_acquisition_cost_house_stock_only",
            ),
        )

    def __str__(self) -> str:
        return self.title

    def fill_defaults(self) -> None:
        """Take a blank department from the design and a blank HS code from the category."""
        if not self.department and self.product_model is not None:
            self.department = self.product_model.department
        if not self.hs_code and self.category_id is not None:
            self.hs_code = self.category.default_hs_code

    def clean(self) -> None:
        self.fill_defaults()
        errors: dict[str, Any] = {}
        if not self.department:
            errors["department"] = "Choose a department; this design has none."
        self._check_design(errors)
        self._check_owner(errors)
        self._check_size_and_year(errors)
        if problems := self._attribute_problems():
            errors["attributes"] = problems
        if errors:
            raise ValidationError(errors)

    def _check_design(self, errors: dict[str, Any]) -> None:
        design = self.product_model
        if design is None:
            return
        if design.brand_id != self.brand_id:
            errors["brand"] = f"{design} is made by {design.brand}."
        if design.category_id != self.category_id:
            errors["category"] = f"{design} is in {design.category}."

    def _check_owner(self, errors: dict[str, Any]) -> None:
        if self.current_owner_id is None:
            return
        house = self.current_owner.is_house_account
        if self.source == Source.HOUSE_STOCK and not house:
            errors["current_owner"] = "House stock belongs to a Samwab house account."
        if self.source == Source.CONSIGNED and house:
            errors["current_owner"] = "A consigned piece belongs to its owner, not to Samwab."
        if self.source == Source.CONSIGNED and self.acquisition_cost_minor is not None:
            errors["acquisition_cost_minor"] = "Only house stock has an acquisition cost."

    def _check_size_and_year(self, errors: dict[str, Any]) -> None:
        if self.size_system and not self.size_label:
            errors["size_label"] = "Give the size in that system, such as 38."
        latest = timezone.now().year + 1
        year = self.production_year
        if year is not None and not FIRST_ERA_YEAR <= year <= latest:
            errors["production_year"] = f"Use a year from {FIRST_ERA_YEAR} to {latest}."

    def _attribute_problems(self) -> list[str]:
        if not isinstance(self.attributes, dict):
            return ['Use a JSON object, such as {"width_cm": 28}.']
        schemas = [self.category.attribute_schema] if self.category_id else []
        if self.product_model is not None:
            schemas.append(self.product_model.attribute_schema)
        problems: list[str] = []
        for schema in schemas:
            for where, message in attribute_errors(schema, self.attributes):
                problems.append(f"{where}: {message}" if where else message)
        return problems


class PieceMaterial(models.Model):
    """Which materials a piece is made of. A material in use can never be deleted."""

    piece = models.ForeignKey(Piece, on_delete=models.CASCADE)
    material = models.ForeignKey(Material, on_delete=models.PROTECT)

    class Meta:
        db_table = "piece_materials"
        constraints = (
            models.UniqueConstraint(fields=("piece", "material"), name="piece_materials_once"),
        )

    def __str__(self) -> str:
        return f"{self.piece}: {self.material}"
