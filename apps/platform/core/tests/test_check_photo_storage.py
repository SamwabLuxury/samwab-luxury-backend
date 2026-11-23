"""python manage.py check_photo_storage: proves the Cloudinary keys work."""

from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from django.test import override_settings

from apps.platform.core.tests.test_storage import URL, FakeCloudinary, patch


def run() -> str:
    out = StringIO()
    call_command("check_photo_storage", stdout=out)
    return out.getvalue()


def test_it_uploads_a_tiny_photo_shows_its_link_and_deletes_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeCloudinary()
    patch(monkeypatch, fake)

    with override_settings(
        CLOUDINARY_URL=URL,
        PHOTO_FOLDER="samwab/local",
        STORAGES={"default": {"BACKEND": "apps.platform.core.storage.CloudinaryStorage"}},
    ):
        output = run()

    [sent] = fake.uploads
    assert sent["public_id"].startswith("samwab/local/checks/")
    assert sent["bytes"].startswith(b"\x89PNG")
    assert fake.destroyed[0]["public_id"] == sent["public_id"]
    assert "https://res.cloudinary.com/samwab-test/image/upload/" in output
    assert "Photo storage is working (Cloudinary, folder samwab/local)." in output


def test_it_says_when_photos_are_kept_on_this_machine() -> None:
    with pytest.raises(CommandError, match="CLOUDINARY_URL"):
        run()  # tests store photos in a folder on disk


def test_it_explains_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeCloudinary()
    fake.fail = True
    patch(monkeypatch, fake)

    with (
        override_settings(
            CLOUDINARY_URL=URL,
            STORAGES={"default": {"BACKEND": "apps.platform.core.storage.CloudinaryStorage"}},
        ),
        pytest.raises(CommandError, match="Check CLOUDINARY_URL"),
    ):
        run()
