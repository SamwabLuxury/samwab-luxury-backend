"""Check and clean a photo before it is kept.

Phone photos carry hidden data: the GPS position where they were taken (EXIF),
the camera, sometimes more (XMP). Pieces are photographed in homes and vaults,
so none of it may reach the public. ``prepare`` turns an upload into a clean
image: the pixels only, upright, in the same format.

Accepted: one still JPEG, PNG or WebP image, up to ``settings.PHOTO_MAX_BYTES``
and Pillow's pixel limit (``Image.MAX_IMAGE_PIXELS``, against "decompression
bombs": small files that unpack into huge images). The format is read from the
bytes, never from the file name or the browser's label.
"""

import hashlib
import io
import warnings
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from PIL import Image, ImageOps, UnidentifiedImageError

from apps.platform.core.exceptions import AppError

# Pillow format name -> file extension
FORMATS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}

MESSAGES = {
    "not_an_image": "This file is not a photo we can read. Upload a JPEG, PNG or WebP image.",
    "format": "Upload a JPEG, PNG or WebP image.",
    "animated": "Upload a still photo, not an animation.",
    "too_large": "This photo is too large. Upload one of {limit} MB or less.",
    "too_many_pixels": "This photo has too many pixels. Upload a smaller one.",
}


class PhotoRejectedError(AppError):
    code = "photo_rejected"
    message = "Upload a JPEG, PNG or WebP image."

    def __init__(self, reason: str) -> None:
        limit = settings.PHOTO_MAX_BYTES // (1024 * 1024)
        super().__init__(MESSAGES[reason].format(limit=limit))
        self.reason = reason


@dataclass(frozen=True)
class PreparedPhoto:
    content: bytes
    extension: str
    width: int
    height: int
    sha256: str


def _open(data: bytes) -> Image.Image:
    """Open and fully decode the image, so a damaged or oversized file fails here."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image = Image.open(io.BytesIO(data), formats=list(FORMATS))
            image.load()
    except (Image.DecompressionBombWarning, Image.DecompressionBombError) as error:
        raise PhotoRejectedError("too_many_pixels") from error
    except UnidentifiedImageError as error:
        # Pillow could not read it as one of the allowed formats: is it an image at all?
        raise PhotoRejectedError(_reason_for_unreadable(data)) from error
    except (OSError, SyntaxError, ValueError) as error:  # truncated or damaged
        raise PhotoRejectedError("not_an_image") from error
    return image


def _reason_for_unreadable(data: bytes) -> str:
    try:
        with Image.open(io.BytesIO(data)):
            return "format"  # an image, but not JPEG, PNG or WebP
    except Exception:
        return "not_an_image"


def prepare(upload: Any) -> PreparedPhoto:
    """Check an uploaded file and return a clean copy, or raise ``PhotoRejectedError``."""
    if upload.size > settings.PHOTO_MAX_BYTES:
        raise PhotoRejectedError("too_large")
    upload.seek(0)
    data = upload.read()
    image = _open(data)
    if getattr(image, "is_animated", False):
        raise PhotoRejectedError("animated")
    file_format = image.format or ""

    # Turn it upright first (its EXIF says how), then keep only the pixels.
    upright = ImageOps.exif_transpose(image)
    clean = Image.new(upright.mode, upright.size)
    clean.paste(upright)
    if "transparency" in upright.info:  # a palette PNG's transparent colour, not metadata
        clean.info["transparency"] = upright.info["transparency"]

    out = io.BytesIO()
    options: dict[str, Any] = {"JPEG": {"quality": 95}, "WEBP": {"quality": 95}}.get(
        file_format, {}
    )
    clean.save(out, file_format, **options)
    content = out.getvalue()
    return PreparedPhoto(
        content=content,
        extension=FORMATS[file_format],
        width=clean.width,
        height=clean.height,
        sha256=hashlib.sha256(content).hexdigest(),
    )
