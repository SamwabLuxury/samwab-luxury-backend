"""Errors that services raise when a business rule says no.

Services know nothing about HTTP. They raise one of these, and the API layer
(``apps/platform/core/api/errors.py``) turns it into the right response.

Each app adds its own errors by extending these, for example::

    class BidTooLow(AppError):
        code = "bid_too_low"
        message = "Your bid is below the lowest amount allowed."
"""


class AppError(Exception):
    """A request we understood but a business rule says no. Becomes HTTP 422."""

    status_code = 422
    code = "error"
    message = "Something went wrong. Please try again."

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
    message = "We couldn't find what you were looking for."


class PermissionDeniedError(AppError):
    """The user is logged in but is not allowed to do this."""

    status_code = 403
    code = "permission_denied"
    message = "Sorry, you don't have access to this."


class ConflictError(AppError):
    """The request clashes with the current state, for example a piece already sold."""

    status_code = 409
    code = "conflict"
    message = "This can't be done right now. Please refresh the page and try again."
