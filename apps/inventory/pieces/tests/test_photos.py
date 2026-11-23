"""Tests for apps.inventory.pieces.photos: every upload is checked and cleaned before it is kept."""

import hashlib
import io
from typing import Any

import pytest
from PIL import Image

from apps.inventory.pieces import photos
from apps.inventory.pieces.tests import images
from apps.inventory.pieces.tests.images import GPS_IFD, upload


def reopen(prepared: photos.PreparedPhoto) -> Image.Image:
    return Image.open(io.BytesIO(prepared.content))


# ---------- accepted photos ----------


def test_a_phone_photo_loses_its_location_and_other_hidden_data() -> None:
    prepared = photos.prepare(upload(images.jpeg(with_location=True)))

    kept = reopen(prepared)
    assert kept.format == "JPEG"
    assert dict(kept.getexif()) == {}
    assert kept.getexif().get_ifd(GPS_IFD) == {}
    assert "xmp" not in kept.info
    assert b"GPSLatitude" not in prepared.content
    assert b"PhoneMaker" not in prepared.content


def test_what_is_kept_is_described_exactly() -> None:
    prepared = photos.prepare(upload(images.jpeg((800, 600))))

    assert (prepared.width, prepared.height) == (800, 600)
    assert prepared.extension == "jpg"
    assert prepared.sha256 == hashlib.sha256(prepared.content).hexdigest()


def test_a_sideways_phone_photo_is_turned_upright_before_its_data_goes() -> None:
    # Orientation 6 means "turn 90 degrees to show it": without it, the photo would lie on its side.
    prepared = photos.prepare(upload(images.jpeg((800, 600), orientation=6)))

    assert (prepared.width, prepared.height) == (600, 800)


def test_a_png_stays_a_png_and_keeps_its_transparency() -> None:
    prepared = photos.prepare(upload(images.png(), "flaw.png", "image/png"))

    assert prepared.extension == "png"
    assert reopen(prepared).mode == "RGBA"


def test_a_webp_stays_a_webp_without_its_hidden_data() -> None:
    prepared = photos.prepare(upload(images.webp(), "shot.webp", "image/webp"))

    assert prepared.extension == "webp"
    assert dict(reopen(prepared).getexif()) == {}


def test_the_name_the_file_had_is_not_trusted() -> None:
    """The format comes from the bytes, never from the file name or the browser's label."""
    prepared = photos.prepare(upload(images.png(), "holiday.jpg", "image/jpeg"))

    assert prepared.extension == "png"


# ---------- refused photos ----------


@pytest.mark.parametrize(
    ("content", "why"),
    [
        (b"just some text, not a picture", "not_an_image"),
        (images.gif(), "format"),
        (images.animated_png(), "animated"),
        (images.jpeg()[:400], "not_an_image"),  # cut off half way
        (b"", "not_an_image"),
    ],
)
def test_anything_that_is_not_one_still_photo_is_refused(content: bytes, why: str) -> None:
    with pytest.raises(photos.PhotoRejectedError) as refused:
        photos.prepare(upload(content))

    assert refused.value.reason == why


def test_a_file_over_the_size_limit_is_refused_before_it_is_opened(
    settings: Any,
) -> None:
    settings.PHOTO_MAX_BYTES = 1_000

    with pytest.raises(photos.PhotoRejectedError) as refused:
        photos.prepare(upload(images.jpeg()))

    assert refused.value.reason == "too_large"


def test_an_image_with_too_many_pixels_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """A small file can unpack into a huge image (a "decompression bomb")."""
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1_000)

    with pytest.raises(photos.PhotoRejectedError) as refused:
        photos.prepare(upload(images.jpeg((100, 100))))

    assert refused.value.reason == "too_many_pixels"


def test_each_refusal_has_a_message_staff_can_act_on() -> None:
    with pytest.raises(photos.PhotoRejectedError) as refused:
        photos.prepare(upload(images.gif()))

    assert "JPEG, PNG or WebP" in str(refused.value)


def test_a_palette_png_keeps_its_see_through_colour() -> None:
    prepared = photos.prepare(upload(images.palette_png(), "logo.png", "image/png"))

    with Image.open(io.BytesIO(prepared.content)) as cleaned:
        assert cleaned.mode == "P"
        assert cleaned.info["transparency"] == 0
