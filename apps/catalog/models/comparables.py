"""Comparable sales: what similar pieces sold for.

They feed the fair-price explainer shown to buyers and owners, and the check
that flags a bid far below the market. Prices are whole US cents: a sale in
another currency is converted on the day it sold.
"""

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.catalog.enums import Department, SaleSource
from apps.catalog.models.catalog import Brand, Category, ProductModel
from apps.core.models import BaseModel
from apps.core.money import DEFAULT_CURRENCY, Money


class ComparableSale(BaseModel):
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="comparable_sales"
    )
    brand = models.ForeignKey(Brand, on_delete=models.PROTECT, related_name="comparable_sales")
    product_model = models.ForeignKey(
        ProductModel,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="comparable_sales",
        verbose_name="design",
        help_text="Leave empty for a piece without a named design.",
    )
    department = models.CharField(max_length=10, choices=Department.choices, blank=True)
    size_label = models.CharField(max_length=20, blank=True, help_text="Such as 28 or EU 38.")
    source = models.CharField(max_length=40, choices=SaleSource.choices)
    source_url = models.URLField(max_length=2000, blank=True)
    condition_grade = models.CharField(max_length=20, blank=True)
    price_minor = models.PositiveBigIntegerField(
        help_text="US cents: $14,200.00 is 1420000. Convert other currencies on the sale date."
    )
    currency = models.CharField(max_length=3, default=DEFAULT_CURRENCY, editable=False)
    sold_on = models.DateField()

    class Meta:
        db_table = "comparable_sales"
        ordering = ("-sold_on", "-id")
        indexes = (
            models.Index(fields=("product_model", "-sold_on"), name="comparables_design_idx"),
            models.Index(fields=("brand", "category", "-sold_on"), name="comparables_brand_idx"),
        )
        constraints = (
            models.CheckConstraint(
                condition=models.Q(price_minor__gt=0), name="comparable_sales_price_above_0"
            ),
            models.CheckConstraint(
                condition=models.Q(currency=DEFAULT_CURRENCY), name="comparable_sales_in_usd"
            ),
            models.CheckConstraint(
                condition=models.Q(source__in=SaleSource.values),
                name="comparable_sales_source_is_known",
            ),
            models.CheckConstraint(
                condition=models.Q(department__in=[*Department.values, ""]),
                name="comparable_sales_department_is_known",
            ),
        )

    def __str__(self) -> str:
        what = str(self.product_model) if self.product_model else self.brand.name
        return f"{what}, {self.price} on {self.sold_on} ({self.source})"

    @property
    def price(self) -> Money:
        return Money(self.price_minor, self.currency)

    def clean(self) -> None:
        errors: dict[str, str] = {}
        if self.sold_on and self.sold_on > timezone.now().date():
            errors["sold_on"] = "A sale cannot be in the future."
        design = self.product_model
        if design is not None:
            if design.brand_id != self.brand_id:
                errors["brand"] = f"{design} is made by {design.brand}."
            if design.category_id != self.category_id:
                errors["category"] = f"{design} is in {design.category}."
        if errors:
            raise ValidationError(errors)
