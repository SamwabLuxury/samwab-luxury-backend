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


class ProtocolStatus(models.TextChoices):
    """A protocol is written as a draft, used while active, and kept once retired."""

    DRAFT = "draft", "Draft"
    ACTIVE = "active", "Active"
    RETIRED = "retired", "Retired"


class ShotKind(models.TextChoices):
    PHOTO = "photo", "Photo"
    READING = "reading", "Reading"


class Instrument(models.TextChoices):
    """What a shot is taken with. Photos use the first four, readings the last three."""

    PHONE = "phone", "Phone camera"
    MACRO_LENS = "macro_lens", "Macro lens"
    MICROSCOPE = "microscope", "Microscope"
    LOUPE = "loupe", "Loupe"
    XRF = "xrf", "XRF metal analyser"
    DIAMOND_TESTER = "diamond_tester", "Diamond tester"
    SCALE = "scale", "Scale"


PHOTO_INSTRUMENTS = (
    Instrument.PHONE,
    Instrument.MACRO_LENS,
    Instrument.MICROSCOPE,
    Instrument.LOUPE,
)
READING_INSTRUMENTS = (Instrument.XRF, Instrument.DIAMOND_TESTER, Instrument.SCALE)


class SaleSource(models.TextChoices):
    """Where a comparable sale happened."""

    SAMWAB = "samwab", "Samwab"
    AUCTION = "auction", "Auction"
    MARKETPLACE = "marketplace", "Marketplace"
