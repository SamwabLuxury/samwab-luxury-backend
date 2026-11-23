"""Prove photo storage works: upload a tiny picture to Cloudinary, show its link,
then delete it. Run it after putting CLOUDINARY_URL in .env or in Render."""

import io
import uuid
from typing import Any

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.core.management.base import BaseCommand, CommandError
from PIL import Image

from apps.platform.core.storage import CloudinaryStorage, PhotoStorageError


class Command(BaseCommand):
    help = "Upload a tiny test photo to Cloudinary, show its link, then delete it."

    def handle(self, *args: Any, **options: Any) -> None:
        photos = storages["default"]
        if not isinstance(photos, CloudinaryStorage):
            raise CommandError(
                "Photos are kept on this machine (media/). "
                "Put CLOUDINARY_URL in .env to use Cloudinary."
            )
        picture = io.BytesIO()
        Image.new("RGB", (2, 2), (184, 144, 92)).save(picture, "PNG")
        try:
            name = photos.save(f"checks/{uuid.uuid4().hex}.png", ContentFile(picture.getvalue()))
            self.stdout.write(f"Uploaded a test photo: {photos.url(name)}")
            photos.delete(name)
        except PhotoStorageError as failure:
            raise CommandError(
                f"{failure.message} Check CLOUDINARY_URL, and that you are online."
            ) from failure
        self.stdout.write("Then deleted it.")
        self.stdout.write(
            self.style.SUCCESS(
                f"Photo storage is working (Cloudinary, folder {settings.PHOTO_FOLDER})."
            )
        )
