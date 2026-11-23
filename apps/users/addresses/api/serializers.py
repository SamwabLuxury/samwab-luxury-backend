from typing import Any, ClassVar

from rest_framework import serializers

from apps.users.addresses.models import Address


class AddressSerializer(serializers.ModelSerializer[Address]):
    """An address as its owner sees and sends it. ``country`` may be lowercase."""

    class Meta:
        model = Address
        fields = (
            "id",
            "label",
            "recipient_name",
            "line1",
            "line2",
            "city",
            "region",
            "postal_code",
            "country",
            "phone",
            "is_default",
        )
        extra_kwargs: ClassVar[dict[str, dict[str, bool]]] = {
            "line2": {"allow_blank": True},
            "phone": {"allow_blank": True},
        }

    def to_internal_value(self, data: Any) -> dict[str, Any]:
        if isinstance(data, dict) and isinstance(data.get("country"), str):
            data = {**data, "country": data["country"].strip().upper()}
        values: dict[str, Any] = super().to_internal_value(data)
        for optional in ("line2", "phone"):  # an empty optional part is stored as nothing
            if values.get(optional) == "":
                values[optional] = None
        return values
