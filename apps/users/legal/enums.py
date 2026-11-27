from django.db import models


class DocumentKind(models.TextChoices):
    """The legal texts in the data model. Each kind has its own numbered versions."""

    TERMS_OF_SERVICE = "terms_of_service", "Terms of service"
    PRIVACY_POLICY = "privacy_policy", "Privacy policy"
    RETURNS_POLICY = "returns_policy", "Returns policy"
    AUTHENTICATION_POLICY = "authentication_policy", "Authentication policy"
    CONSIGNMENT_AGREEMENT = "consignment_agreement", "Consignment agreement"
    STORAGE_TERMS = "storage_terms", "Storage terms"
    BUYER_AUTHENTICATION_FORM = "buyer_authentication_form", "Buyer authentication form"


# Documents she signs by typing her full name.
NEEDS_SIGNATURE = frozenset(
    {DocumentKind.CONSIGNMENT_AGREEMENT, DocumentKind.BUYER_AUTHENTICATION_FORM}
)
# Documents signed once per order rather than once per account.
PER_ORDER = frozenset({DocumentKind.BUYER_AUTHENTICATION_FORM})


class ConsentKind(models.TextChoices):
    """What a person can agree to, and take back, at any time."""

    MARKETING = "marketing", "Marketing emails"
    TRAINING_IMAGES = "training_images", "Photos used to train our authentication model"
