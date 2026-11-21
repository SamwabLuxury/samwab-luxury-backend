"""Tests for apps.idempotency.services: claiming a key, replaying, and the rules around it."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.idempotency import services
from apps.idempotency.exceptions import (
    IdempotencyKeyInProgressError,
    IdempotencyKeyReusedError,
)
from apps.idempotency.models import IdempotencyKey

pytestmark = pytest.mark.django_db

ENDPOINT = "POST /api/v1/orders/"


@pytest.fixture
def ada() -> User:
    return User.objects.create_user("ada@example.com", "correct-horse-9")


def claim(
    user: User, key: str = "key-1", *, body: object = None, endpoint: str = ENDPOINT
) -> services.Claim:
    return services.claim(
        user=user,
        key=key,
        endpoint=endpoint,
        request_sha256=services.fingerprint(body if body is not None else {"a": 1}),
    )


# ---------- the fingerprint ----------


def test_the_fingerprint_ignores_the_order_of_fields() -> None:
    assert services.fingerprint({"a": 1, "b": [1, 2]}) == services.fingerprint(
        {"b": [1, 2], "a": 1}
    )


def test_the_fingerprint_changes_with_any_value() -> None:
    assert services.fingerprint({"a": 1}) != services.fingerprint({"a": 2})
    assert services.fingerprint({"a": 1}) != services.fingerprint({"a": 1}, query={"x": ["1"]})


def test_the_fingerprint_is_64_hex_characters() -> None:
    value = services.fingerprint({"price": {"amount": 100, "currency": "USD"}})

    assert len(value) == 64
    assert set(value) <= set("0123456789abcdef")


# ---------- claiming ----------


def test_a_new_key_is_claimed_for_24_hours(ada: User) -> None:
    before = timezone.now()

    result = claim(ada)

    assert result.replay is False
    row = IdempotencyKey.objects.get()
    assert (row.user, row.key, row.endpoint) == (ada, "key-1", ENDPOINT)
    assert row.response_status is None
    assert before + timedelta(hours=24) <= row.expires_at <= timezone.now() + timedelta(hours=24)


def test_the_same_key_while_the_first_request_runs_is_a_conflict(ada: User) -> None:
    claim(ada)

    with pytest.raises(IdempotencyKeyInProgressError):
        claim(ada)


def test_a_finished_request_is_replayed(ada: User) -> None:
    first = claim(ada)
    services.complete(first.row, status=201, body={"id": "abc"})

    again = claim(ada)

    assert again.replay is True
    assert (again.row.response_status, again.row.response_body) == (201, {"id": "abc"})
    assert IdempotencyKey.objects.count() == 1


def test_the_same_key_with_another_body_is_refused(ada: User) -> None:
    services.complete(claim(ada, body={"a": 1}).row, status=201, body={})

    with pytest.raises(IdempotencyKeyReusedError):
        claim(ada, body={"a": 2})


def test_the_same_key_on_another_endpoint_is_refused(ada: User) -> None:
    services.complete(claim(ada).row, status=201, body={})

    with pytest.raises(IdempotencyKeyReusedError):
        claim(ada, endpoint="POST /api/v1/bids/")


def test_another_person_may_use_the_same_key(ada: User) -> None:
    grace = User.objects.create_user("grace@example.com", "correct-horse-9")
    claim(ada)

    assert claim(grace).replay is False
    assert IdempotencyKey.objects.count() == 2


def test_an_expired_key_starts_again_as_new(ada: User) -> None:
    first = claim(ada, body={"a": 1})
    services.complete(first.row, status=201, body={"old": True})
    IdempotencyKey.objects.update(expires_at=timezone.now() - timedelta(seconds=1))

    result = claim(ada, body={"a": 2})

    assert result.replay is False
    row = IdempotencyKey.objects.get()
    assert row.response_status is None
    assert row.response_body is None
    assert row.request_sha256 == services.fingerprint({"a": 2})
    assert row.expires_at > timezone.now()


def test_a_key_left_running_by_a_crashed_request_can_be_taken_over(ada: User) -> None:
    claim(ada)
    IdempotencyKey.objects.update(created_at=timezone.now() - services.CLAIM_TIMEOUT)

    assert claim(ada).replay is False


def test_a_recent_unfinished_key_is_not_taken_over(ada: User) -> None:
    claim(ada)
    IdempotencyKey.objects.update(
        created_at=timezone.now() - services.CLAIM_TIMEOUT + timedelta(seconds=5)
    )

    with pytest.raises(IdempotencyKeyInProgressError):
        claim(ada)


def test_releasing_a_key_lets_the_request_be_tried_again(ada: User) -> None:
    services.release(claim(ada).row)

    assert not IdempotencyKey.objects.exists()
    assert claim(ada).replay is False


# ---------- clean-up ----------


def test_delete_expired_removes_only_old_keys(ada: User) -> None:
    claim(ada, "old")
    claim(ada, "new")
    IdempotencyKey.objects.filter(key="old").update(expires_at=timezone.now())

    assert services.delete_expired() == 1
    assert list(IdempotencyKey.objects.values_list("key", flat=True)) == ["new"]


def test_the_command_deletes_expired_keys(ada: User, capsys: pytest.CaptureFixture[str]) -> None:
    from django.core.management import call_command

    claim(ada)
    IdempotencyKey.objects.update(expires_at=timezone.now() - timedelta(hours=1))

    call_command("delete_expired_idempotency_keys")

    assert not IdempotencyKey.objects.exists()
    assert "Deleted 1 expired idempotency key" in capsys.readouterr().out


# ---------- the table ----------


def test_the_table_follows_the_data_model(ada: User) -> None:
    from django.db import IntegrityError, transaction

    assert IdempotencyKey._meta.db_table == "idempotency_keys"
    claim(ada)
    with pytest.raises(IntegrityError), transaction.atomic():
        IdempotencyKey.objects.create(
            user=ada,
            key="key-1",
            endpoint=ENDPOINT,
            request_sha256="0" * 64,
            expires_at=timezone.now(),
        )


def test_when_two_requests_take_over_an_old_key_only_one_wins(
    ada: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    claim(ada)
    IdempotencyKey.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    # The other request reset the row first, so this one's conditional update matches nothing.
    monkeypatch.setattr(services, "_start_fresh", lambda *args, **kwargs: False)

    with pytest.raises(IdempotencyKeyInProgressError):
        claim(ada)


def test_a_key_shows_its_endpoint_and_value(ada: User) -> None:
    assert str(claim(ada).row) == f"{ENDPOINT} key-1"
