"""Errors that services raise when a business rule says no.

Services know nothing about HTTP. They raise one of these, and the API layer
(``apps/platform/core/api/errors.py``) turns it into the right response.

Each app adds its own errors by extending these, for example::

    class BidTooLow(AppError):
        code = "bid_too_low"
        message = "The bid is below the lowest amount allowed."
"""


class AppError(Exception):
    """A request we understood but a business rule says no. Becomes HTTP 422."""

    status_code = 422
    code = "error"
    message = "The request could not be completed."

    def __init__(self, message: str | None = None, *, code: str | None = None) -> None:
        if message is not None:
            self.message = message
        if code is not None:
            self.code = code
        super().__init__(self.message)


class NotFoundError(AppError):
    """The thing asked for does not exist, or this user may not know it exists."""

    status_code = 404
    code = "not_found"
    message = "Not found."


class PermissionDeniedError(AppError):
    """The user is logged in but is not allowed to do this."""

    status_code = 403
    code = "permission_denied"
    message = "You do not have permission to do this."


class ConflictError(AppError):
    """The request clashes with the current state, for example a piece already sold."""

    status_code = 409
    code = "conflict"
    message = "The request conflicts with the current state."
