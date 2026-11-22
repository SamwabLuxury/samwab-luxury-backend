from django.db import models


class SignupIntent(models.TextChoices):
    """The sign-up page someone came through. It starts her onboarding and grants nothing."""

    BUYER = "buyer", "Buyer"
    OWNER = "owner", "Owner (seller)"
    DEALER = "dealer", "Dealer"


class NextStep(models.TextChoices):
    """Onboarding steps the web app can send someone to next."""

    ACCEPT_TERMS = "accept_terms", "Accept the consignment terms"
    IDENTITY_CHECK = "identity_check", "Complete the ID check"
    PAYOUT_ACCOUNT = "payout_account", "Set up payouts"
    DEALER_APPLICATION = "dealer_application", "Apply to become a dealer"
    AWAIT_DEALER_DECISION = "await_dealer_decision", "Wait for the dealer decision"
