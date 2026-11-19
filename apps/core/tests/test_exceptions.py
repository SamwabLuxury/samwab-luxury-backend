"""Tests for apps.core.exceptions: the errors services raise."""

import pytest

from apps.core.exceptions import AppError, ConflictError, NotFoundError, PermissionDeniedError


@pytest.mark.parametrize(
    ("error_class", "status", "code"),
    [
        (AppError, 422, "error"),
        (NotFoundError, 404, "not_found"),
        (PermissionDeniedError, 403, "permission_denied"),
        (ConflictError, 409, "conflict"),
    ],
)
def test_defaults(error_class: type[AppError], status: int, code: str) -> None:
    error = error_class()

    assert error.status_code == status
    assert error.code == code
    assert error.message
    assert str(error) == error.message


def test_every_error_is_an_app_error() -> None:
    for error_class in (NotFoundError, PermissionDeniedError, ConflictError):
        assert issubclass(error_class, AppError)


def test_message_and_code_can_be_set_for_one_error() -> None:
    error = ConflictError("This piece is already sold.", code="piece_sold")

    assert error.message == "This piece is already sold."
    assert error.code == "piece_sold"
    assert error.status_code == 409
    assert str(error) == "This piece is already sold."


def test_setting_one_error_does_not_change_the_class() -> None:
    ConflictError("Changed.", code="changed")

    assert ConflictError().code == "conflict"
    assert ConflictError().message == "The request conflicts with the current state."


def test_a_subclass_sets_its_own_code_and_message() -> None:
    class BidTooLowError(AppError):
        code = "bid_too_low"
        message = "The bid is below the lowest amount allowed."

    error = BidTooLowError()

    assert (error.status_code, error.code) == (422, "bid_too_low")
    assert str(error) == "The bid is below the lowest amount allowed."


def test_it_can_be_caught_as_a_normal_exception() -> None:
    with pytest.raises(AppError):
        raise NotFoundError()
