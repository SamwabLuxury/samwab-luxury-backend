"""Real image files for the photo tests, made with Pillow in memory.

A phone photo carries hidden extras: the GPS position where it was taken (in
EXIF) and sometimes more in XMP. ``jpeg(with_location=True)`` makes such a file.
"""

import io

from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

GPS_IFD = 0x8825
ORIENTATION = 0x0112
XMP = (
    b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><exif:GPSLatitude>6,27.0N</exif:GPSLatitude></x:xmpmeta>'
)


def _exif(*, location: bool, orientation: int | None) -> Image.Exif:
    exif = Image.Exif()
    exif[0x010F] = "PhoneMaker"  # camera make
    if location:
        exif.get_ifd(GPS_IFD).update({1: "N", 2: (6.0, 27.0, 0.0), 3: "E", 4: (3.0, 23.0, 0.0)})
    if orientation is not None:
        exif[ORIENTATION] = orientation
    return exif


def jpeg(
    size: tuple[int, int] = (800, 600),
    *,
    with_location: bool = True,
    orientation: int | None = None,
) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, (180, 120, 60)).save(
        out,
        "JPEG",
        exif=_exif(location=with_location, orientation=orientation),
        xmp=XMP if with_location else b"",
    )
    return out.getvalue()


def png(size: tuple[int, int] = (640, 480)) -> bytes:
    out = io.BytesIO()
    Image.new("RGBA", size, (10, 20, 30, 128)).save(out, "PNG")
    return out.getvalue()


def palette_png(size: tuple[int, int] = (64, 48)) -> bytes:
    """A palette PNG whose colour 0 is see-through, as many logos and cut-outs are."""
    out = io.BytesIO()
    Image.new("P", size, 0).save(out, "PNG", transparency=0)
    return out.getvalue()


def webp(size: tuple[int, int] = (640, 480)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, (40, 50, 60)).save(
        out, "WEBP", exif=_exif(location=True, orientation=None)
    )
    return out.getvalue()


def gif() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (64, 64)).save(out, "GIF")
    return out.getvalue()


def animated_png() -> bytes:
    out = io.BytesIO()
    frames = [Image.new("RGB", (64, 64), colour) for colour in ((255, 0, 0), (0, 255, 0))]
    frames[0].save(out, "PNG", save_all=True, append_images=frames[1:])
    return out.getvalue()


def upload(
    content: bytes, name: str = "IMG_0042.jpg", content_type: str = "image/jpeg"
) -> SimpleUploadedFile:
    return SimpleUploadedFile(name, content, content_type=content_type)
