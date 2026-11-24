"""Photo storage on Cloudinary: what we send, the links we build, and failures."""

from collections.abc import Iterator
from io import BytesIO
from typing import Any

import cloudinary.exceptions
import pytest
from django.core.files.base import ContentFile
from django.test import override_settings

from apps.platform.core.storage import CloudinaryStorage, PhotoStorageError, photo_links

URL = "cloudinary://123456:not-a-real-secret@samwab-test"


class FakeCloudinary:
    """Stands in for cloudinary.uploader: records calls, answers like Cloudinary."""

    def __init__(self) -> None:
        self.uploads: list[dict[str, Any]] = []
        self.destroyed: list[dict[str, Any]] = []
        self.fail = False

    def upload(self, file: Any, **options: Any) -> dict[str, Any]:
        if self.fail:
            raise cloudinary.exceptions.Error("Invalid Signature")
        self.uploads.append({"bytes": file.read(), **options})
        return {"public_id": options["public_id"], "secure_url": "https://res.cloudinary.com/x"}

    def destroy(self, public_id: str, **options: Any) -> dict[str, str]:
        if self.fail:
            raise cloudinary.exceptions.Error("Invalid Signature")
        self.destroyed.append({"public_id": public_id, **options})
        return {"result": "ok"}


@pytest.fixture
def cloud(monkeypatch: pytest.MonkeyPatch) -> FakeCloudinary:
    fake = FakeCloudinary()
    patch(monkeypatch, fake)
    return fake


def patch(monkeypatch: pytest.MonkeyPatch, fake: FakeCloudinary) -> None:
    monkeypatch.setattr("cloudinary.uploader.upload", fake.upload)
    monkeypatch.setattr("cloudinary.uploader.destroy", fake.destroy)


@pytest.fixture
def photos() -> Iterator[CloudinaryStorage]:
    with override_settings(CLOUDINARY_URL=URL, PHOTO_FOLDER="samwab/local"):
        yield CloudinaryStorage()


def test_saving_uploads_the_bytes_under_our_name(
    cloud: FakeCloudinary, photos: CloudinaryStorage
) -> None:
    name = photos.save("pieces/abc/0001.jpg", ContentFile(b"jpeg bytes"))

    assert name == "pieces/abc/0001.jpg"
    [sent] = cloud.uploads
    assert sent["bytes"] == b"jpeg bytes"
    assert sent["public_id"] == "samwab/local/pieces/abc/0001"  # images: no extension
    assert sent["asset_folder"] == "samwab/local/pieces/abc"
    assert sent["resource_type"] == "image"
    assert sent["type"] == "upload"
    assert sent["overwrite"] is False  # a saved photo is never replaced


def test_the_link_is_https_on_cloudinary(photos: CloudinaryStorage) -> None:
    link = photos.url("pieces/abc/0001.jpg")

    assert (
        link
        == "https://res.cloudinary.com/samwab-test/image/upload/v1/samwab/local/pieces/abc/0001.jpg"
    )
    assert "not-a-real-secret" not in link and "123456" not in link


def test_deleting_removes_it_from_cloudinary(
    cloud: FakeCloudinary, photos: CloudinaryStorage
) -> None:
    photos.delete("pieces/abc/0001.png")

    assert cloud.destroyed == [
        {"public_id": "samwab/local/pieces/abc/0001", "resource_type": "image", "invalidate": True}
    ]


def test_exists_needs_no_call_because_names_are_new_every_time(
    cloud: FakeCloudinary, photos: CloudinaryStorage
) -> None:
    assert photos.exists("pieces/abc/0001.jpg") is False
    assert cloud.uploads == cloud.destroyed == []


def test_a_cloudinary_failure_becomes_one_clear_error_without_the_secret(
    cloud: FakeCloudinary, photos: CloudinaryStorage
) -> None:
    cloud.fail = True

    with pytest.raises(PhotoStorageError) as failed:
        photos.save("pieces/abc/0001.jpg", ContentFile(b"x"))

    assert failed.value.code == "photo_storage_unavailable"
    assert failed.value.status_code == 502
    assert "not-a-real-secret" not in str(failed.value)


def test_photos_cannot_be_read_back_through_storage(photos: CloudinaryStorage) -> None:
    with pytest.raises(NotImplementedError, match="link"):
        photos.open("pieces/abc/0001.jpg")


@pytest.mark.parametrize(
    "bad", ["", "not-a-url", "cloudinary://only-a-cloud", "https://123:abc@cloud"]
)
def test_a_malformed_cloudinary_url_is_refused(bad: str) -> None:
    with (
        override_settings(CLOUDINARY_URL=bad),
        pytest.raises(PhotoStorageError, match="CLOUDINARY_URL"),
    ):
        CloudinaryStorage()


def test_bytes_are_sent_from_the_start_of_the_file(
    cloud: FakeCloudinary, photos: CloudinaryStorage
) -> None:
    content = ContentFile(b"abcdef")
    content.file = BytesIO(b"abcdef")
    content.file.read(3)  # someone read part of it already

    photos.save("pieces/abc/0002.webp", content)

    assert cloud.uploads[0]["bytes"] == b"abcdef"


def test_a_failed_delete_becomes_our_error(
    cloud: FakeCloudinary, photos: CloudinaryStorage
) -> None:
    cloud.fail = True

    with pytest.raises(PhotoStorageError):
        photos.delete("pieces/abc/0001.jpg")


# ---------- sized links (E7) ----------


def test_a_sized_link_fits_a_box_and_lets_cloudinary_choose_format_and_quality(
    photos: CloudinaryStorage,
) -> None:
    link = photos.sized_url("pieces/abc/0001.jpg", 400)

    # Cloudinary's docs: resize first, then q_auto and f_auto as the last two parts;
    # `limit` keeps the shape and never makes a small photo bigger.
    assert link == (
        "https://res.cloudinary.com/samwab-test/image/upload/"
        "c_limit,h_400,w_400/q_auto/f_auto/v1/samwab/local/pieces/abc/0001.jpg"
    )


SIZES = {"thumb": 400, "medium": 1200, "zoom": 2400}


def test_every_size_from_the_setting_gets_a_link_on_cloudinary(cloud: FakeCloudinary) -> None:
    with override_settings(
        CLOUDINARY_URL=URL,
        PHOTO_FOLDER="samwab/local",
        PHOTO_SIZES=SIZES,
        STORAGES={
            "default": {"BACKEND": "apps.platform.core.storage.CloudinaryStorage"},
            "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
        },
    ):
        links = photo_links("pieces/abc/0001.jpg")

    assert list(links) == ["thumb", "medium", "zoom"]
    assert "c_limit,h_400,w_400" in links["thumb"]
    assert "c_limit,h_1200,w_1200" in links["medium"]
    assert "c_limit,h_2400,w_2400" in links["zoom"]
    assert cloud.uploads == [] and cloud.destroyed == []  # links cost no call


def test_without_cloudinary_every_size_is_the_photo_itself() -> None:
    with override_settings(PHOTO_SIZES=SIZES):
        links = photo_links("pieces/abc/0001.jpg")

    assert links == dict.fromkeys(SIZES, "/media/pieces/abc/0001.jpg")
