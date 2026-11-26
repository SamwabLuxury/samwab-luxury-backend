"""Build E19: a sold piece keeps its page, so a listing records when it sold.

Listings already sold get the time their order was paid (the latest paid order of the
listing), or, if no paid order is found, the time the listing last changed (which is
when it was marked sold). Reversing only removes the column.
"""

from typing import Any

from django.db import migrations, models
from django.db.models import Max


def fill_sold_at(apps: Any, schema_editor: Any) -> None:
    listing_model = apps.get_model("listings", "Listing")
    order_model = apps.get_model("orders", "Order")
    sold = listing_model.objects.filter(status="sold", sold_at__isnull=True)
    for listing in sold.iterator():
        paid = order_model.objects.filter(listing_id=listing.pk, paid_at__isnull=False).aggregate(
            last=Max("paid_at")
        )["last"]
        listing_model.objects.filter(pk=listing.pk).update(sold_at=paid or listing.updated_at)


class Migration(migrations.Migration):
    dependencies = [
        ("listings", "0005_alter_listing_options"),
        ("orders", "0002_order_number_counters"),
    ]

    operations = [
        migrations.AddField(
            model_name="listing",
            name="sold_at",
            field=models.DateTimeField(
                blank=True,
                editable=False,
                help_text="When a paid order sold it (E19).",
                null=True,
            ),
        ),
        migrations.RunPython(fill_sold_at, migrations.RunPython.noop),
    ]
