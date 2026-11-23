"""Tests for piece photos: the media table and the services that add, change and delete them."""

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any

import pytest
from django.core.files.storage import default_storage
from django.db import IntegrityError, transaction

from apps.inventory.pieces import photos, services
from apps.inventory.pieces.models import Media, Piece
from apps.inventory.pieces.tests import images
from apps.inventory.pieces.tests.helpers import make_piece
from apps.inventory.pieces.tests.images import upload
from apps.platform.audit.models import AuditEvent
from apps.users.accounts.models import User
from apps.users.accounts.tests.helpers import make_staff

pytestmark = pytest.mark.django_db

Capture = Callable[..., AbstractContextManager[list[Callable[[], Any]]]]


@pytest.fixture
def clerk() -> User:
    user: User = make_staff("intake@samwab.com", "intake_staff")
    return user


@pytest.fixture
def piece() -> Piece:
    return make_piece()


def add(piece: Piece, clerk: User, content: bytes | None = None, kind: str = "listing") -> Media:
    prepared = photos.prepare(upload(content or images.jpeg()))
    return services.add_photo(piece, prepared, kind=kind, by=clerk)


# ---------- the table ----------


def test_the_table_follows_the_data_model() -> None:
    assert Media._meta.db_table == "media"
    assert Media._meta.get_field("file").column == "storage_key"


@pytest.mark.parametrize(
    "bad",
    [
        {"kind": "selfie"},
        {"sha256": "abc"},
        {"width": 0},
        {"height": -3},
    ],
)
def test_the_database_refuses_impossible_rows(piece: Piece, bad: dict[str, Any]) -> None:
    values: dict[str, Any] = {
        "piece": piece,
        "kind": "listing",
        "file": "pieces/x.jpg",
        "sha256": "0" * 64,
        "width": 10,
        "height": 10,
    }
    values.update(bad)

    with pytest.raises(IntegrityError), transaction.atomic():
        Media.objects.create(**values)


def test_a_piece_with_photos_cannot_be_deleted_from_under_them(piece: Piece, clerk: User) -> None:
    from django.db.models import ProtectedError

    add(piece, clerk)

    with pytest.raises(ProtectedError):
        piece.delete()


# ---------- adding ----------


def test_a_photo_is_stored_under_a_new_name_with_its_details(piece: Piece, clerk: User) -> None:
    media = add(piece, clerk, images.jpeg((800, 600)))

    media.refresh_from_db()
    assert media.stored_name.startswith(f"pieces/{piece.id}/")
    assert media.stored_name.endswith(".jpg")
    assert "IMG_0042" not in media.stored_name  # the uploader's file name is never kept
    assert (media.width, media.height, media.kind, media.sort_order) == (800, 600, "listing", 1)
    assert default_storage.exists(media.stored_name)
    with default_storage.open(media.stored_name) as stored:
        assert b"GPSLatitude" not in stored.read()


def test_each_new_photo_goes_last(piece: Piece, clerk: User) -> None:
    first, second = add(piece, clerk), add(piece, clerk, kind="flaw")

    assert (first.sort_order, second.sort_order) == (1, 2)
    assert list(piece.photos.all()) == [first, second]


def test_adding_a_photo_is_audited(piece: Piece, clerk: User) -> None:
    media = add(piece, clerk)

    event = AuditEvent.objects.get()
    assert (event.action, event.object_id, event.actor) == ("pieces.media.created", media.id, clerk)
    assert event.changes["piece_id"] == {"to": str(piece.id)}
    assert event.changes["sha256"] == {"to": media.sha256}


def test_if_saving_the_photo_fails_its_file_is_removed(
    piece: Piece, clerk: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepared = photos.prepare(upload(images.jpeg()))
    stored: list[str] = []
    real_save = default_storage.save

    def save_and_remember(name: str, content: Any, **kwargs: Any) -> str:
        stored.append(real_save(name, content, **kwargs))
        return stored[-1]

    def broken_audit(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("the database refused the row")

    monkeypatch.setattr(default_storage, "save", save_and_remember)
    monkeypatch.setattr("apps.inventory.pieces.services.audit.record_saved", broken_audit)

    with pytest.raises(RuntimeError):
        services.add_photo(piece, prepared, kind="listing", by=clerk)

    assert len(stored) == 1
    assert not default_storage.exists(stored[0])
    assert not Media.objects.exists()


# ---------- changing and deleting ----------


def test_changing_kind_and_order_is_audited(piece: Piece, clerk: User) -> None:
    media = add(piece, clerk)
    AuditEvent.objects.all()  # created event exists

    services.update_photo(media, kind="condition", sort_order=5, by=clerk)

    event = AuditEvent.objects.get(action="pieces.media.changed")
    assert event.changes == {
        "kind": {"from": "listing", "to": "condition"},
        "sort_order": {"from": 1, "to": 5},
    }


def test_saving_a_photo_without_a_change_records_nothing(piece: Piece, clerk: User) -> None:
    media = add(piece, clerk)

    services.update_photo(media, kind="listing", sort_order=1, by=clerk)

    assert not AuditEvent.objects.filter(action="pieces.media.changed").exists()


def test_deleting_a_photo_removes_the_file_after_the_change_is_saved(
    piece: Piece, clerk: User, django_capture_on_commit_callbacks: Capture
) -> None:
    media = add(piece, clerk)
    name, media_id = media.stored_name, media.id

    with django_capture_on_commit_callbacks(execute=True):
        services.delete_photo(media, by=clerk)

    assert not Media.objects.exists()
    assert not default_storage.exists(name)
    event = AuditEvent.objects.get(action="pieces.media.deleted")
    assert event.object_id == media_id


def test_a_cancelled_delete_keeps_the_file(piece: Piece, clerk: User) -> None:
    media = add(piece, clerk)

    with pytest.raises(RuntimeError), transaction.atomic():
        services.delete_photo(media, by=clerk)
        raise RuntimeError("cancelled")

    assert Media.objects.exists()
    assert default_storage.exists(media.stored_name)


def test_a_photo_has_a_web_address(piece: Piece, clerk: User) -> None:
    media = add(piece, clerk)

    assert media.file.url == f"/media/{media.stored_name}"
    assert str(media) == f"{piece} · listing photo 1"
