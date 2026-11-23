"""Photos of a piece: the ``media`` table of the data model.

Files are kept through Django's default storage: a folder on your machine, a
cloud bucket on the live site. Only ``apps.inventory.pieces.services`` adds or removes
them, after ``apps.inventory.pieces.photos`` has checked and cleaned the upload.
"""

from django.db import models
from django.db.models.functions import Length

from apps.inventory.pieces.enums import MediaKind
from apps.inventory.pieces.models.pieces import Piece
from apps.platform.core.models import BaseModel


class Media(BaseModel):
    piece = models.ForeignKey(Piece, on_delete=models.PROTECT, related_name="photos")
    kind = models.CharField(max_length=20, choices=MediaKind.choices)
    # The data model calls this column storage_key: the file's name in the storage.
    file = models.FileField(db_column="storage_key", max_length=500)
    sha256 = models.CharField(max_length=64, help_text="Fingerprint of the stored file")
    width = models.PositiveIntegerField()
    height = models.PositiveIntegerField()
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "media"
        ordering = ("sort_order", "id")
        verbose_name = "photo"
        constraints = (
            models.CheckConstraint(
                condition=models.Q(kind__in=MediaKind.values), name="media_kind_known"
            ),
            models.CheckConstraint(
                condition=models.lookups.Exact(Length("sha256"), 64), name="media_sha256_is_64"
            ),
            models.CheckConstraint(
                condition=models.Q(width__gt=0, height__gt=0), name="media_has_a_size"
            ),
        )
        indexes = (models.Index(fields=("piece", "sort_order"), name="media_piece_order_idx"),)

    @property
    def stored_name(self) -> str:
        """The file's name in the storage. Every saved photo has one."""
        return self.file.name or ""

    def __str__(self) -> str:
        return f"{self.piece} · {self.kind} photo {self.sort_order}"
