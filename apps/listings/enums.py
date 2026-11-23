from django.db import models


class ListingStatus(models.TextChoices):
    """Moved only through the listing services (see ``state.py``)."""

    DRAFT = "draft", "Draft"
    LIVE = "live", "Live"
    MATCHED = "matched", "Matched to a bid"
    SOLD = "sold", "Sold"
    WITHDRAWN = "withdrawn", "Withdrawn"
    EXPIRED = "expired", "Expired"


# A piece has at most one listing in these statuses at a time.
OPEN_STATUSES = (ListingStatus.DRAFT, ListingStatus.LIVE, ListingStatus.MATCHED)


class Fulfilment(models.TextChoices):
    """Where the piece goes to the buyer from."""

    FROM_VAULT = "from_vault", "From the vault"
    FROM_HOME = "from_home", "From the owner's home"


class AcquisitionSource(models.TextChoices):
    """How the owner found Samwab."""

    SEARCH = "search", "Search"
    SOCIAL = "social", "Social media"
    REFERRAL = "referral", "Referral"
    WHATSAPP = "whatsapp", "WhatsApp"
    EVENT = "event", "Event"
    MARKETPLACE = "marketplace", "Marketplace"
    OTHER = "other", "Other"
