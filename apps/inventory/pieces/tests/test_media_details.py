"""A photo's optional name and note (E7): "Stamp", and one line on what it shows.

They label the "Look closer" viewer on the piece page. Staff write them, or leave
them empty (the team, 24 Nov).
"""

from typing import Any

import pytest
from django.core.exceptions import ValidationError
from django.test import Client

from apps.inventory.pieces import photos, services
from apps.inventory.pieces.models import Media, Piece
from apps.inventory.pieces.tests import images
from apps.inventory.pieces.tests.helpers import make_piece
from apps.inventory.pieces.tests.images import upload
from apps.inventory.pieces.tests.test_admin_photos import photo_rows, save
from apps.platform.audit.models import AuditEvent
from apps.users.accounts.models import User
from apps.users.accounts.tests.helpers import admin_login, make_staff

pytestmark = pytest.mark.django_db

NOTE = "Shallow; the grain still runs through the letters. A deep, glossy stamp would flatten it."


@pytest.fixture
def clerk() -> User:
    user: User = make_staff("intake@samwab.com", "intake_staff")
    return user


@pytest.fixture
def piece() -> Piece:
    return make_piece()


def add(piece: Piece, clerk: User, **details: Any) -> Media:
    prepared = photos.prepare(upload(images.jpeg()))
    return services.add_photo(piece, prepared, kind="listing", by=clerk, **details)


def test_a_new_photo_has_no_name_or_note(piece: Piece, clerk: User) -> None:
    media = add(piece, clerk)

    assert (media.label, media.caption) == ("", "")


def test_a_photo_can_be_added_with_a_name_and_note(piece: Piece, clerk: User) -> None:
    media = add(piece, clerk, label="Stamp", caption=NOTE)

    media.refresh_from_db()
    assert (media.label, media.caption) == ("Stamp", NOTE)
    created = AuditEvent.objects.get(action="pieces.media.created")
    assert created.changes["label"] == {"to": "Stamp"}
    assert created.changes["caption"] == {"to": NOTE}


def test_changing_the_name_and_note_is_audited(piece: Piece, clerk: User) -> None:
    media = add(piece, clerk)

    services.update_photo(
        media, kind="listing", sort_order=1, label="Stamp", caption=NOTE, by=clerk
    )

    event = AuditEvent.objects.get(action="pieces.media.changed")
    assert event.changes == {
        "label": {"from": "", "to": "Stamp"},
        "caption": {"from": "", "to": NOTE},
    }


def test_leaving_out_the_name_and_note_keeps_them(piece: Piece, clerk: User) -> None:
    media = add(piece, clerk, label="Stamp", caption=NOTE)

    services.update_photo(media, kind="condition", sort_order=1, by=clerk)

    media.refresh_from_db()
    assert (media.kind, media.label, media.caption) == ("condition", "Stamp", NOTE)


def test_spaces_around_a_name_and_note_are_trimmed(piece: Piece, clerk: User) -> None:
    media = add(piece, clerk, label="  Stamp ", caption=f"\n{NOTE}  ")

    assert (media.label, media.caption) == ("Stamp", NOTE)


@pytest.mark.parametrize(("field", "length"), [("label", 61), ("caption", 301)])
def test_a_name_or_note_too_long_is_refused(
    piece: Piece, clerk: User, field: str, length: int
) -> None:
    media = add(piece, clerk)

    with pytest.raises(ValidationError) as refused:
        services.update_photo(
            media, kind="listing", sort_order=1, by=clerk, **{field: "x" * length}
        )

    assert field in refused.value.message_dict
    media.refresh_from_db()
    assert getattr(media, field) == ""
    assert not AuditEvent.objects.filter(action="pieces.media.changed").exists()


def test_the_longest_name_and_note_fit(piece: Piece, clerk: User) -> None:
    media = add(piece, clerk, label="é" * 60, caption="ü" * 300)

    media.refresh_from_db()
    assert (len(media.label), len(media.caption)) == (60, 300)


# ---------- in the admin ----------


@pytest.fixture
def clerk_client(client: Client, clerk: User) -> Client:
    admin_login(client, clerk)
    return client


def test_staff_name_a_photo_when_they_upload_it(clerk_client: Client, piece: Piece) -> None:
    response = save(
        clerk_client,
        piece,
        **photo_rows(
            {"upload": upload(images.jpeg()), "kind": "listing", "label": "Whole", "caption": NOTE}
        ),
    )

    assert response.status_code == 302, response.content.decode()[:3000]
    assert list(piece.photos.values_list("label", "caption")) == [("Whole", NOTE)]


def test_staff_change_a_saved_photos_name_and_note(clerk_client: Client, piece: Piece) -> None:
    save(clerk_client, piece, **photo_rows({"upload": upload(images.jpeg()), "kind": "listing"}))
    media = Media.objects.get()

    response = save(
        clerk_client,
        piece,
        **photo_rows(
            {
                "id": str(media.id),
                "piece": str(piece.id),
                "kind": "listing",
                "sort_order": "1",
                "label": "Stamp",
                "caption": NOTE,
            },
            initial=1,
        ),
    )

    assert response.status_code == 302, response.content.decode()[:3000]
    media.refresh_from_db()
    assert (media.label, media.caption) == ("Stamp", NOTE)
    assert AuditEvent.objects.filter(action="pieces.media.changed").count() == 1


def test_the_admin_explains_the_name_and_note(clerk_client: Client, piece: Piece) -> None:
    page = clerk_client.get(f"/admin/pieces/piece/{piece.id}/change/").content.decode()

    assert 'name="photos-0-label"' in page
    assert 'name="photos-0-caption"' in page
    assert "optional" in page.lower()
