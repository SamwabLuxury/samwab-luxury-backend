"""Tests for capture protocols: the shots and readings staff take of each piece.

A protocol belongs to a category (its default) or to one design. It is written
as a draft, then made active; changing it later means a new version, so the
evidence already taken always matches the protocol it was taken under.
"""

from typing import Any

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.inventory.catalog import selectors, services
from apps.inventory.catalog.exceptions import (
    ProtocolHasNoShotsError,
    ProtocolNotActiveError,
    ProtocolNotDraftError,
)
from apps.inventory.catalog.models import CaptureProtocol, CaptureShot
from apps.inventory.catalog.tests.helpers import (
    make_category,
    make_product_model,
    make_protocol,
    make_shot,
)
from apps.users.accounts.models import User

pytestmark = pytest.mark.django_db


@pytest.fixture
def editor() -> User:
    return User.objects.create_user("editor@samwab.com", "correct-horse-9")


def messages(error: pytest.ExceptionInfo[ValidationError]) -> dict[str, list[str]]:
    return error.value.message_dict


# ---------- tables ----------


def test_tables_use_the_data_model_names() -> None:
    assert CaptureProtocol._meta.db_table == "capture_protocols"
    assert CaptureShot._meta.db_table == "capture_shots"


def test_protocol_and_shot_defaults() -> None:
    protocol = make_protocol()
    shot = make_shot(protocol)

    assert protocol.status == "draft"
    assert protocol.version == 1
    assert protocol.product_model is None
    assert str(protocol) == "Bags (default) v1, draft"
    assert shot.kind == "photo"
    assert shot.is_required is True
    assert shot.magnification is None
    assert shot.instructions == ""
    assert str(shot) == "heat_stamp: Heat stamp"


def test_a_design_protocol_shows_the_design() -> None:
    kelly = make_product_model("Kelly 28")

    protocol = make_protocol(category=kelly.category, product_model=kelly)

    assert str(protocol) == "Hermès Kelly 28 v1, draft"


# ---------- database rules ----------


def test_one_version_number_per_category_default() -> None:
    bags = make_category("Bags")
    make_protocol(category=bags, version=1)

    with pytest.raises(IntegrityError), transaction.atomic():
        make_protocol(category=bags, version=1)


def test_one_version_number_per_design() -> None:
    kelly = make_product_model()
    make_protocol(category=kelly.category, product_model=kelly, version=1)

    with pytest.raises(IntegrityError), transaction.atomic():
        make_protocol(category=kelly.category, product_model=kelly, version=1)


def test_a_category_default_and_a_design_can_both_have_version_1() -> None:
    kelly = make_product_model()
    make_protocol(category=kelly.category, version=1)

    make_protocol(category=kelly.category, product_model=kelly, version=1)

    assert CaptureProtocol.objects.count() == 2


def test_only_one_active_protocol_per_category_default() -> None:
    bags = make_category("Bags")
    make_protocol(category=bags, version=1, status="active")

    with pytest.raises(IntegrityError), transaction.atomic():
        make_protocol(category=bags, version=2, status="active")


def test_only_one_active_protocol_per_design() -> None:
    kelly = make_product_model()
    make_protocol(category=kelly.category, product_model=kelly, version=1, status="active")

    with pytest.raises(IntegrityError), transaction.atomic():
        make_protocol(category=kelly.category, product_model=kelly, version=2, status="active")


@pytest.mark.parametrize(
    "fields",
    [
        {"status": "deleted"},
        {"version": 0},
    ],
)
def test_database_refuses_a_bad_protocol(fields: dict[str, Any]) -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        make_protocol(**fields)


def test_shot_codes_are_unique_in_a_protocol() -> None:
    protocol = make_protocol()
    make_shot(protocol, code="heat_stamp")

    with pytest.raises(IntegrityError), transaction.atomic():
        make_shot(protocol, code="heat_stamp")


def test_two_protocols_can_use_the_same_shot_code() -> None:
    first = make_protocol(version=1)
    second = make_protocol(category=first.category, version=2)

    make_shot(first, code="heat_stamp")
    make_shot(second, code="heat_stamp")

    assert CaptureShot.objects.count() == 2


@pytest.mark.parametrize(
    "fields",
    [
        {"kind": "video"},
        {"instrument": "camera"},
        {"kind": "photo", "instrument": "scale"},
        {"kind": "reading", "instrument": "loupe"},
        {"magnification": 0},
        {"code": "Heat Stamp"},
        {"code": ""},
    ],
)
def test_database_refuses_a_bad_shot(fields: dict[str, Any]) -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        make_shot(make_protocol(), **fields)


@pytest.mark.parametrize(
    ("kind", "instrument"),
    [
        ("photo", "phone"),
        ("photo", "macro_lens"),
        ("photo", "microscope"),
        ("photo", "loupe"),
        ("reading", "xrf"),
        ("reading", "diamond_tester"),
        ("reading", "scale"),
    ],
)
def test_each_kind_takes_its_own_instruments(kind: str, instrument: str) -> None:
    shot = make_shot(make_protocol(), kind=kind, instrument=instrument)

    assert (shot.kind, shot.instrument) == (kind, instrument)


# ---------- form rules ----------


def test_a_design_protocol_must_use_the_design_category() -> None:
    kelly = make_product_model()
    watches = make_category("Watches")

    protocol = CaptureProtocol(category=watches, product_model=kelly, version=1)
    with pytest.raises(ValidationError) as error:
        protocol.full_clean()

    assert "product_model" in messages(error)


def test_shots_can_only_change_while_the_protocol_is_a_draft() -> None:
    protocol = make_protocol(status="active")
    shot = CaptureShot(
        protocol=protocol, code="hardware", name="Hardware", instrument="phone", sort_order=2
    )

    with pytest.raises(ValidationError) as error:
        shot.full_clean()

    assert "protocol" in messages(error)


def test_a_shot_code_must_be_a_lowercase_code() -> None:
    shot = CaptureShot(
        protocol=make_protocol(), code="Heat Stamp", name="x", instrument="phone", sort_order=1
    )

    with pytest.raises(ValidationError) as error:
        shot.full_clean()

    assert "code" in messages(error)


def test_a_photo_cannot_use_a_reading_instrument_in_the_form() -> None:
    shot = CaptureShot(
        protocol=make_protocol(), code="weight", name="Weight", instrument="scale", sort_order=1
    )

    with pytest.raises(ValidationError) as error:
        shot.full_clean()

    assert "instrument" in messages(error)


# ---------- services: the life of a protocol ----------


def test_create_protocol_numbers_versions_per_scope(editor: User) -> None:
    kelly = make_product_model()
    bags = kelly.category

    first = services.create_protocol(category=bags, by=editor)
    second = services.create_protocol(category=bags, by=editor)
    for_kelly = services.create_protocol(category=bags, product_model=kelly, by=editor)

    assert (first.version, second.version, for_kelly.version) == (1, 2, 1)
    assert {first.status, second.status, for_kelly.status} == {"draft"}


def test_create_protocol_checks_the_design_belongs_to_the_category(editor: User) -> None:
    kelly = make_product_model()

    with pytest.raises(ValidationError):
        services.create_protocol(category=make_category("Watches"), product_model=kelly, by=editor)

    assert not CaptureProtocol.objects.exists()


def test_activate_makes_a_draft_active(editor: User) -> None:
    protocol = make_protocol()
    make_shot(protocol)

    services.activate_protocol(protocol, by=editor)

    protocol.refresh_from_db()
    assert protocol.status == "active"


def test_activate_retires_the_one_it_replaces(editor: User) -> None:
    old = make_protocol(version=1, status="active")
    new = make_protocol(category=old.category, version=2)
    make_shot(new)

    services.activate_protocol(new, by=editor)

    old.refresh_from_db()
    new.refresh_from_db()
    assert (old.status, new.status) == ("retired", "active")


def test_activating_a_design_protocol_leaves_the_category_default_alone(editor: User) -> None:
    kelly = make_product_model()
    default = make_protocol(category=kelly.category, status="active")
    for_kelly = make_protocol(category=kelly.category, product_model=kelly)
    make_shot(for_kelly)

    services.activate_protocol(for_kelly, by=editor)

    default.refresh_from_db()
    assert default.status == "active"


def test_a_protocol_without_shots_cannot_be_activated(editor: User) -> None:
    protocol = make_protocol()

    with pytest.raises(ProtocolHasNoShotsError) as error:
        services.activate_protocol(protocol, by=editor)

    assert error.value.code == "protocol_has_no_shots"
    assert error.value.status_code == 422
    protocol.refresh_from_db()
    assert protocol.status == "draft"


def test_a_protocol_without_required_shots_cannot_be_activated(editor: User) -> None:
    protocol = make_protocol()
    make_shot(protocol, is_required=False)

    with pytest.raises(ProtocolHasNoShotsError):
        services.activate_protocol(protocol, by=editor)


@pytest.mark.parametrize("status", ["active", "retired"])
def test_only_a_draft_can_be_activated(editor: User, status: str) -> None:
    protocol = make_protocol(status=status)

    with pytest.raises(ProtocolNotDraftError) as error:
        services.activate_protocol(protocol, by=editor)

    assert (error.value.code, error.value.status_code) == ("protocol_not_draft", 409)


def test_activate_reads_the_status_from_the_database(editor: User) -> None:
    """Two staff working from the same page: the second click must not act on old data."""
    protocol = make_protocol()
    make_shot(protocol)
    stale = CaptureProtocol.objects.get(pk=protocol.pk)
    services.activate_protocol(protocol, by=editor)

    with pytest.raises(ProtocolNotDraftError):
        services.activate_protocol(stale, by=editor)


def test_retire_an_active_protocol(editor: User) -> None:
    protocol = make_protocol(status="active")

    services.retire_protocol(protocol, by=editor)

    protocol.refresh_from_db()
    assert protocol.status == "retired"


@pytest.mark.parametrize("status", ["draft", "retired"])
def test_only_an_active_protocol_can_be_retired(editor: User, status: str) -> None:
    protocol = make_protocol(status=status)

    with pytest.raises(ProtocolNotActiveError) as error:
        services.retire_protocol(protocol, by=editor)

    assert (error.value.code, error.value.status_code) == ("protocol_not_active", 409)


def test_new_draft_copies_the_shots_into_the_next_version(editor: User) -> None:
    protocol = make_protocol(status="active")
    make_shot(protocol, code="heat_stamp", sort_order=1, magnification=10, instrument="loupe")
    make_shot(protocol, code="weight", kind="reading", instrument="scale", sort_order=2)

    draft = services.new_draft_from(protocol, by=editor)

    assert (draft.version, draft.status) == (2, "draft")
    assert draft.category == protocol.category
    copied = list(draft.shots.values_list("code", "instrument", "magnification", "sort_order"))
    assert copied == [("heat_stamp", "loupe", 10, 1), ("weight", "scale", None, 2)]
    assert protocol.shots.count() == 2  # the original keeps its own shots


def test_new_draft_follows_the_latest_version_not_the_one_copied(editor: User) -> None:
    v1 = make_protocol(version=1, status="retired")
    make_protocol(category=v1.category, version=2, status="active")

    draft = services.new_draft_from(v1, by=editor)

    assert draft.version == 3


# ---------- selector: which protocol applies ----------


class TestActiveProtocolFor:
    @pytest.fixture
    def kelly(self) -> Any:
        return make_product_model("Kelly 28")

    def test_a_design_with_its_own_protocol_uses_it(self, kelly: Any) -> None:
        make_protocol(category=kelly.category, status="active")
        own = make_protocol(category=kelly.category, product_model=kelly, status="active")

        assert selectors.active_protocol_for(category=kelly.category, product_model=kelly) == own

    def test_otherwise_the_category_default_applies(self, kelly: Any) -> None:
        default = make_protocol(category=kelly.category, status="active")
        make_protocol(category=kelly.category, product_model=kelly, status="draft")

        found = selectors.active_protocol_for(category=kelly.category, product_model=kelly)

        assert found == default

    def test_a_piece_without_a_design_uses_the_category_default(self, kelly: Any) -> None:
        default = make_protocol(category=kelly.category, status="active")

        assert selectors.active_protocol_for(category=kelly.category) == default

    def test_nothing_active_means_none(self, kelly: Any) -> None:
        make_protocol(category=kelly.category, status="retired")

        assert selectors.active_protocol_for(category=kelly.category, product_model=kelly) is None

    def test_another_category_default_never_applies(self, kelly: Any) -> None:
        make_protocol(category=make_category("Watches"), status="active")

        assert selectors.active_protocol_for(category=kelly.category) is None

    def test_shots_come_in_order(self, kelly: Any) -> None:
        protocol = make_protocol(category=kelly.category, status="active")
        make_shot(protocol, code="b_second", sort_order=2)
        make_shot(protocol, code="a_first", sort_order=1)

        found = selectors.active_protocol_for(category=kelly.category)

        assert found is not None
        assert [shot.code for shot in found.shots.all()] == ["a_first", "b_second"]
