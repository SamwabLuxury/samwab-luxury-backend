"""Tests for apps.platform.core.models.BaseModel.

BaseModel has no table, so these tests use a small model built on it.
Nothing here is saved, so no database is needed.
"""

import uuid

from django.db import models

from apps.platform.core.ids import new_uuid
from apps.platform.core.models import BaseModel


class Sample(BaseModel):
    """A model that exists only for these tests."""

    class Meta:
        app_label = "core"

    def __str__(self) -> str:
        return str(self.id)


def test_base_model_is_abstract() -> None:
    assert BaseModel._meta.abstract is True


def test_a_model_built_on_it_has_exactly_the_three_shared_columns() -> None:
    names = [field.name for field in Sample._meta.get_fields()]

    assert names == ["id", "created_at", "updated_at"]


def test_id_is_a_uuid_primary_key_that_cannot_be_edited() -> None:
    field = Sample._meta.get_field("id")

    assert isinstance(field, models.UUIDField)
    assert field.primary_key is True
    assert field.editable is False
    assert field.default is new_uuid


def test_id_exists_before_the_object_is_saved() -> None:
    sample = Sample()

    assert isinstance(sample.id, uuid.UUID)
    assert sample.id.version == 7


def test_each_object_gets_its_own_id() -> None:
    assert Sample().id != Sample().id


def test_created_at_is_set_once_and_updated_at_on_every_save() -> None:
    created_at = Sample._meta.get_field("created_at")
    updated_at = Sample._meta.get_field("updated_at")

    assert isinstance(created_at, models.DateTimeField)
    assert created_at.auto_now_add is True
    assert created_at.auto_now is False
    assert isinstance(updated_at, models.DateTimeField)
    assert updated_at.auto_now is True
