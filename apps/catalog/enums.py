from django.db import models


class Department(models.TextChoices):
    """Who a design is made for. Its pieces start with this value."""

    WOMEN = "women", "Women"
    MEN = "men", "Men"
    UNISEX = "unisex", "Unisex"


class Storage(models.TextChoices):
    """How the vault stores a piece of this category unless told otherwise."""

    SHELF = "shelf", "Shelf"
    HANGING = "hanging", "Hanging"
    SAFE = "safe", "Safe"
