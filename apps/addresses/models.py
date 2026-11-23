"""A delivery address a person keeps on their account.

The recipient's name, the street lines and the phone number are encrypted in
the database (decision D5); city, region, postal code and country stay plain,
because sales tax and delivery rules need to read them. Each person has at most
one default address.
"""

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models

from apps.core.fields import EncryptedTextField
from apps.core.models import BaseModel

country_validator = RegexValidator(r"^[A-Z]{2}$", "Use the two-letter country code, such as NG.")
phone_validator = RegexValidator(
    r"^\+?[0-9][0-9 ()-]{5,30}$", "Use digits, spaces and + ( ) - only, such as +234 803 000 0000."
)


class Address(BaseModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="addresses"
    )
    label = models.CharField(max_length=40, blank=True, help_text="Such as Home or Office.")
    recipient_name = EncryptedTextField(db_column="recipient_name_enc", max_length=160)
    line1 = EncryptedTextField(db_column="line1_enc", max_length=200)
    line2 = EncryptedTextField(db_column="line2_enc", max_length=200, null=True, blank=True)
    city = models.CharField(max_length=100)
    region = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=2, validators=[country_validator])
    phone = EncryptedTextField(
        db_column="phone_enc", max_length=32, null=True, blank=True, validators=[phone_validator]
    )
    is_default = models.BooleanField(default=False)

    class Meta:
        db_table = "addresses"
        ordering = ("-id",)
        verbose_name_plural = "addresses"
        constraints = (
            models.UniqueConstraint(
                fields=("user",),
                condition=models.Q(is_default=True),
                name="addresses_one_default_per_user",
            ),
            models.CheckConstraint(
                condition=models.Q(country__regex=r"^[A-Z]{2}$"), name="addresses_country_code"
            ),
        )

    def __str__(self) -> str:
        # No name or street: this text can end up in logs and admin pages.
        place = f"{self.city}, {self.country}"
        return f"{self.label} · {place}" if self.label else place
