"""Intake staff add, change and remove a piece's photos on its admin page."""

from typing import Any

import pytest
from django.test import Client

from apps.inventory.pieces.models import Media, Piece
from apps.inventory.pieces.tests import images
from apps.inventory.pieces.tests.helpers import make_piece
from apps.inventory.pieces.tests.images import upload
from apps.platform.audit.models import AuditEvent
from apps.users.accounts.models import User
from apps.users.accounts.tests.helpers import admin_login, make_staff

pytestmark = pytest.mark.django_db

PREFIX = "photos"


@pytest.fixture
def clerk() -> User:
    user: User = make_staff("intake@samwab.com", "intake_staff")
    return user


@pytest.fixture
def clerk_client(client: Client, clerk: User) -> Client:
    admin_login(client, clerk)
    return client


def piece_form(piece: Piece) -> dict[str, Any]:
    """The piece's own fields, unchanged, and an empty materials inline."""
    return {
        "title": piece.title,
        "brand": str(piece.brand_id),
        "category": str(piece.category_id),
        "department": piece.department,
        "attributes": "{}",
        "source": piece.source,
        "home_country": piece.home_country,
        "current_owner": str(piece.current_owner_id),
        "currency": "USD",
        "piecematerial_set-TOTAL_FORMS": "0",
        "piecematerial_set-INITIAL_FORMS": "0",
    }


def photo_rows(*rows: dict[str, Any], initial: int = 0) -> dict[str, Any]:
    data: dict[str, Any] = {
        f"{PREFIX}-TOTAL_FORMS": str(len(rows)),
        f"{PREFIX}-INITIAL_FORMS": str(initial),
    }
    for index, row in enumerate(rows):
        data.update({f"{PREFIX}-{index}-{name}": value for name, value in row.items()})
    return data


def save(client: Client, piece: Piece, **rows: Any) -> Any:
    return client.post(f"/admin/pieces/piece/{piece.id}/change/", {**piece_form(piece), **rows})


def test_staff_upload_photos_on_the_piece_page(clerk_client: Client) -> None:
    piece = make_piece()

    response = save(
        clerk_client,
        piece,
        **photo_rows(
            {"upload": upload(images.jpeg()), "kind": "listing"},
            {"upload": upload(images.png(), "flaw.png", "image/png"), "kind": "flaw"},
        ),
    )

    assert response.status_code == 302, response.content.decode()[:3000]
    kept = list(piece.photos.values_list("kind", "sort_order"))
    assert kept == [("listing", 1), ("flaw", 2)]
    assert AuditEvent.objects.filter(action="pieces.media.created").count() == 2


def test_a_file_that_is_not_a_photo_shows_a_message_and_saves_nothing(clerk_client: Client) -> None:
    piece = make_piece()

    response = save(
        clerk_client,
        piece,
        **photo_rows(
            {"upload": upload(b"not a picture", "notes.txt", "text/plain"), "kind": "listing"}
        ),
    )

    assert response.status_code == 200
    assert "JPEG, PNG or WebP" in response.content.decode()
    assert not Media.objects.exists()


def test_a_new_row_needs_a_photo(clerk_client: Client) -> None:
    piece = make_piece()

    response = save(clerk_client, piece, **photo_rows({"kind": "listing", "sort_order": "3"}))

    assert response.status_code == 200
    assert "Choose a photo to upload." in response.content.decode()


def test_staff_change_a_photos_kind_and_order(clerk_client: Client) -> None:
    piece = make_piece()
    save(clerk_client, piece, **photo_rows({"upload": upload(images.jpeg()), "kind": "listing"}))
    media = Media.objects.get()

    response = save(
        clerk_client,
        piece,
        **photo_rows(
            {"id": str(media.id), "piece": str(piece.id), "kind": "condition", "sort_order": "4"},
            initial=1,
        ),
    )

    assert response.status_code == 302, response.content.decode()[:3000]
    media.refresh_from_db()
    assert (media.kind, media.sort_order) == ("condition", 4)
    assert AuditEvent.objects.filter(action="pieces.media.changed").count() == 1


def test_a_saved_photo_cannot_be_swapped_for_another_file(clerk_client: Client) -> None:
    piece = make_piece()
    save(clerk_client, piece, **photo_rows({"upload": upload(images.jpeg()), "kind": "listing"}))
    media = Media.objects.get()
    before = media.sha256

    response = save(
        clerk_client,
        piece,
        **photo_rows(
            {
                "id": str(media.id),
                "piece": str(piece.id),
                "kind": "listing",
                "sort_order": "1",
                "upload": upload(images.jpeg((300, 300))),
            },
            initial=1,
        ),
    )

    assert response.status_code == 200
    assert "delete this photo and add a new one" in response.content.decode()
    media.refresh_from_db()
    assert media.sha256 == before


def test_staff_remove_a_photo(
    clerk_client: Client, django_capture_on_commit_callbacks: Any
) -> None:
    piece = make_piece()
    save(clerk_client, piece, **photo_rows({"upload": upload(images.jpeg()), "kind": "listing"}))
    media = Media.objects.get()

    with django_capture_on_commit_callbacks(execute=True):
        response = save(
            clerk_client,
            piece,
            **photo_rows(
                {
                    "id": str(media.id),
                    "piece": str(piece.id),
                    "kind": "listing",
                    "sort_order": "1",
                    "DELETE": "on",
                },
                initial=1,
            ),
        )

    assert response.status_code == 302
    assert not Media.objects.exists()
    assert AuditEvent.objects.filter(action="pieces.media.deleted").count() == 1


def test_the_piece_page_shows_a_preview_of_each_photo(clerk_client: Client) -> None:
    piece = make_piece()
    save(clerk_client, piece, **photo_rows({"upload": upload(images.jpeg()), "kind": "listing"}))
    media = Media.objects.get()

    html = clerk_client.get(f"/admin/pieces/piece/{piece.id}/change/").content.decode()

    assert f'src="{media.file.url}"' in html


def test_a_catalog_editor_cannot_change_photos(client: Client) -> None:
    admin_login(client, make_staff("ed@samwab.com", "catalog_editor"))

    assert client.get("/admin/pieces/piece/").status_code == 403


def test_a_photo_row_not_yet_saved_has_no_preview() -> None:
    from django.contrib import admin as django_admin

    from apps.inventory.pieces.admin import PhotoInline

    inline = PhotoInline(Piece, django_admin.site)

    assert inline.preview(Media()) == "-"


def test_if_photo_storage_is_down_staff_see_why_and_nothing_is_half_saved(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    from apps.inventory.pieces import services
    from apps.platform.core.storage import PhotoStorageError

    def down(*args: object, **kwargs: object) -> None:
        raise PhotoStorageError()

    monkeypatch.setattr(services, "add_photo", down)
    admin_login(client, make_staff("intake@samwab.com", "intake_staff"))
    piece = make_piece()

    rows = photo_rows({"upload": upload(images.jpeg()), "kind": "listing"})
    response = client.post(
        f"/admin/pieces/piece/{piece.id}/change/", {**piece_form(piece), **rows}, follow=True
    )

    assert "could not be saved because photo storage did not answer" in response.content.decode()
    assert not Media.objects.exists()
