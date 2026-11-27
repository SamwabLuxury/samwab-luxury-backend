from django.db import models


class FlawSeverity(models.TextChoices):
    """How much a flaw matters, as shown on the condition map."""

    MINOR = "minor", "Minor"
    MODERATE = "moderate", "Moderate"
    MAJOR = "major", "Major"
