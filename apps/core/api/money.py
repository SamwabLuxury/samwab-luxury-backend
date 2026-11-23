from rest_framework import serializers

from apps.core.money import Money


class MoneySerializer(serializers.Serializer[Money]):
    """Money in the API: ``{"amount": 1250000, "currency": "USD"}``, the amount in cents."""

    amount = serializers.IntegerField(
        source="amount_minor", min_value=0, help_text="Minor units (cents)."
    )
    currency = serializers.CharField(help_text="ISO 4217 code, such as USD.")
