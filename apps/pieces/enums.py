from django.db import models


class Source(models.TextChoices):
    """Where a piece came from."""

    HOUSE_STOCK = "house_stock", "House stock (Samwab owns it)"
    CONSIGNED = "consigned", "Consigned (an owner sells it through Samwab)"


class SizeSystem(models.TextChoices):
    EU = "EU", "EU"
    US = "US", "US"
    UK = "UK", "UK"
    IT = "IT", "IT"
    FR = "FR", "FR"
    JP = "JP", "JP"
    RING_US = "ring_US", "US ring"


class AuthenticationBasis(models.TextChoices):
    """How the piece's authenticity is established. Set at intake."""

    SAMWAB_CHECKED = "samwab_checked", "Checked by Samwab"
    BRAND_CARD = "brand_card", "Brand card"
    BUYER_AUTHENTICATED = "buyer_authenticated", "Authenticated by the buyer"


class ConditionGrade(models.TextChoices):
    NEW = "new", "New"
    EXCELLENT = "excellent", "Excellent"
    VERY_GOOD = "very_good", "Very good"
    GOOD = "good", "Good"
    FAIR = "fair", "Fair"


class VerificationStatus(models.TextChoices):
    UNVERIFIED = "unverified", "Unverified"
    VERIFIED = "verified", "Verified"
    NOT_AUTHENTIC = "not_authentic", "Not authentic"


class CustodyStatus(models.TextChoices):
    """Where the piece physically is. Moved only through ``services.move_custody``."""

    WITH_OWNER = "with_owner", "With its owner"
    IN_TRANSIT = "in_transit", "In transit"
    AT_INTAKE = "at_intake", "At intake"
    IN_VAULT = "in_vault", "In the vault"
    WITH_BUYER = "with_buyer", "With the buyer"
