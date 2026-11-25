"""E8: a comparable sale's grade becomes one of the five grades.

Before E8 it was free text. Each stored value is converted once: "Very good",
"very-good" and "VERY GOOD" become ``very_good``; anything that is not one of the
five grades (a letter, "v. good", "Mint") is cleared, so staff can set it again.
Clearing loses nothing the price explainer could have used, since it only
compares exact grades. Going back keeps the converted values.
"""

from typing import Any

from django.db import migrations, models

GRADES = ("new", "excellent", "very_good", "good", "fair")


def normalise_grade(typed: str) -> str:
    """The grade value for text staff typed, or "" when it is not one of the five."""
    value = "_".join(typed.strip().lower().replace("-", " ").replace("_", " ").split())
    return value if value in GRADES else ""


def convert_grades(apps: Any, schema_editor: Any) -> None:
    ComparableSale = apps.get_model("catalog", "ComparableSale")
    for sale in ComparableSale.objects.exclude(condition_grade__in=[*GRADES, ""]).only(
        "id", "condition_grade"
    ):
        sale.condition_grade = normalise_grade(sale.condition_grade)
        sale.save(update_fields=["condition_grade"])


class Migration(migrations.Migration):
    dependencies = [("catalog", "0002_capture_and_comparables")]

    operations = [
        migrations.RunPython(convert_grades, migrations.RunPython.noop, elidable=True),
        migrations.AlterField(
            model_name="comparablesale",
            name="condition_grade",
            field=models.CharField(
                blank=True,
                choices=[
                    ("new", "New"),
                    ("excellent", "Excellent"),
                    ("very_good", "Very good"),
                    ("good", "Good"),
                    ("fair", "Fair"),
                ],
                help_text="The grade of the piece that sold. The price explainer only compares the same grade.",
                max_length=20,
            ),
        ),
        migrations.AddConstraint(
            model_name="comparablesale",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("condition_grade__in", ["new", "excellent", "very_good", "good", "fair", ""])
                ),
                name="comparable_sales_grade_is_known",
            ),
        ),
    ]
