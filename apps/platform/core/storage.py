"""Photo storage on Cloudinary, through Django's storage layer.

Models keep using ``FileField`` and ``default_storage``; this class decides where
the bytes go. A stored name such as ``pieces/<piece id>/<uuid>.jpg`` becomes the
Cloudinary public ID ``<PHOTO_FOLDER>/pieces/<piece id>/<uuid>`` (Cloudinary's
docs: an image's public ID has no file extension), and the link is built from it
without a call to Cloudinary.

Settings: ``CLOUDINARY_URL`` (``cloudinary://<api key>:<api secret>@<cloud name>``,
from the Cloudinary console; never in Git) and ``PHOTO_FOLDER`` (``samwab/local``
on developers' machines, ``samwab/live`` on the live site). Photos are public
links: buyers see them anyway. The official ``cloudinary`` SDK does the work.
"""

import logging
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlsplit

import cloudinary
import cloudinary.exceptions
import cloudinary.uploader
import cloudinary.utils
from django.conf import settings
from django.core.files import File
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible

from apps.platform.core.exceptions import AppError

logger = logging.getLogger(__name__)


class PhotoStorageError(AppError):
    """Cloudinary refused or could not be reached, or its settings are wrong. HTTP 502."""

    status_code = 502
    code = "photo_storage_unavailable"
    message = "The photo could not be stored. Please try again."


def _configure(url: str) -> str:
    """Point the Cloudinary SDK at our account. Returns the folder for log lines."""
    parts = urlsplit(url)
    if parts.scheme != "cloudinary" or not (parts.username and parts.password and parts.hostname):
        raise PhotoStorageError(
            "CLOUDINARY_URL must look like cloudinary://<api key>:<api secret>@<cloud name>."
        )
    cloudinary.config(
        cloud_name=parts.hostname,
        api_key=parts.username,
        api_secret=parts.password,
        secure=True,  # https links
        analytics=False,  # no tracking parameter on links
    )
    return parts.hostname


@deconstructible
class CloudinaryStorage(Storage):
    def __init__(self) -> None:
        self.cloud = _configure(settings.CLOUDINARY_URL)
        self.folder = settings.PHOTO_FOLDER.strip("/")

    def _public_id(self, name: str) -> str:
        return f"{self.folder}/{PurePosixPath(name).with_suffix('')}"

    def _save(self, name: str, content: File) -> str:  # type: ignore[type-arg]
        content.seek(0)
        public_id = self._public_id(name)
        try:
            cloudinary.uploader.upload(
                content,
                public_id=public_id,
                asset_folder=str(PurePosixPath(public_id).parent),
                resource_type="image",
                type="upload",
                overwrite=False,
            )
        except cloudinary.exceptions.Error as failure:
            logger.warning("cloudinary upload of %s failed: %s", public_id, type(failure).__name__)
            raise PhotoStorageError() from failure
        return name

    def delete(self, name: str) -> None:
        public_id = self._public_id(name)
        try:
            cloudinary.uploader.destroy(public_id, resource_type="image", invalidate=True)
        except cloudinary.exceptions.Error as failure:
            logger.warning("cloudinary delete of %s failed: %s", public_id, type(failure).__name__)
            raise PhotoStorageError() from failure

    def exists(self, name: str) -> bool:
        # Every stored name has a new random part, so it never exists yet.
        return False

    def url(self, name: str | None) -> str:
        path = PurePosixPath(name or "")
        link, _ = cloudinary.utils.cloudinary_url(
            self._public_id(str(path)),
            format=path.suffix.lstrip("."),
            resource_type="image",
            type="upload",
            secure=True,
        )
        return str(link)

    def _open(self, name: str, mode: str = "rb") -> Any:
        raise NotImplementedError("Photos on Cloudinary are read through their link (url).")
