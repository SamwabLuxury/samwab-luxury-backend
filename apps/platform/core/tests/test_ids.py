"""Tests for apps.platform.core.ids: every ID must be a valid, unique, ordered UUID version 7."""

import threading
import time
import uuid

import pytest

from apps.platform.core import ids


def timestamp_ms_of(value: uuid.UUID) -> int:
    """Read the time (in milliseconds) stored in the first 48 bits of a UUID version 7."""
    return value.int >> 80


def test_new_uuid_returns_a_version_7_uuid() -> None:
    value = ids.new_uuid()

    assert isinstance(value, uuid.UUID)
    assert value.version == 7
    assert value.variant == uuid.RFC_4122


def test_id_carries_the_current_time() -> None:
    before_ms = time.time_ns() // 1_000_000
    value = ids._fallback_uuid7()
    after_ms = time.time_ns() // 1_000_000

    assert before_ms <= timestamp_ms_of(value) <= after_ms


def test_many_ids_are_all_different() -> None:
    values = [ids._fallback_uuid7() for _ in range(10_000)]

    assert len(set(values)) == 10_000


def test_ids_made_one_after_another_sort_in_that_order() -> None:
    values = [ids._fallback_uuid7() for _ in range(2_000)]

    assert values == sorted(values)


def test_ids_made_in_the_same_millisecond_stay_unique_and_ordered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ids, "_last_timestamp_ms", 0)
    monkeypatch.setattr(ids, "_last_counter", 0)
    monkeypatch.setattr(ids, "_now_ms", lambda: 1_800_000_000_000)

    values = [ids._fallback_uuid7() for _ in range(500)]

    assert len(set(values)) == 500
    assert values == sorted(values)
    assert {timestamp_ms_of(value) for value in values} == {1_800_000_000_000}


def test_ids_stay_ordered_when_the_clock_goes_backwards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ids, "_last_timestamp_ms", 0)
    monkeypatch.setattr(ids, "_last_counter", 0)
    clock_ms = iter([1_800_000_000_500, 1_800_000_000_100, 1_800_000_000_000])
    monkeypatch.setattr(ids, "_now_ms", lambda: next(clock_ms))

    first, second, third = (ids._fallback_uuid7() for _ in range(3))

    assert first < second < third
    assert timestamp_ms_of(third) == 1_800_000_000_500


def test_full_counter_moves_to_the_next_millisecond(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ids, "_last_timestamp_ms", 1_800_000_000_000)
    monkeypatch.setattr(ids, "_last_counter", ids._COUNTER_MAX)
    monkeypatch.setattr(ids, "_now_ms", lambda: 1_800_000_000_000)

    value = ids._fallback_uuid7()

    assert value.version == 7
    assert timestamp_ms_of(value) == 1_800_000_000_001


def test_ids_made_by_many_threads_are_all_different() -> None:
    results: list[uuid.UUID] = []
    results_lock = threading.Lock()

    def make_ids() -> None:
        made = [ids._fallback_uuid7() for _ in range(2_000)]
        with results_lock:
            results.extend(made)

    threads = [threading.Thread(target=make_ids) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(results) == 16_000
    assert len(set(results)) == 16_000


def test_new_uuid_uses_pythons_own_uuid7_when_it_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    fixed = uuid.UUID("018f0000-0000-7000-8000-000000000000")
    monkeypatch.setattr(ids, "_stdlib_uuid7", lambda: fixed)

    assert ids.new_uuid() == fixed


def test_new_uuid_uses_our_builder_when_python_has_no_uuid7(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ids, "_stdlib_uuid7", None)

    assert ids.new_uuid().version == 7
