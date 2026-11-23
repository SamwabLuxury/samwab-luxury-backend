"""Errors for the Idempotency-Key header. Status codes follow the IETF draft
"The Idempotency-Key HTTP Header Field" (draft-ietf-httpapi-idempotency-key-header).
"""

from apps.platform.core.exceptions import AppError, ConflictError


class IdempotencyKeyMissingError(AppError):
    status_code = 400
    code = "idempotency_key_missing"
    message = "This request needs an Idempotency-Key header: a new random value, such as a UUID."


class IdempotencyKeyInvalidError(AppError):
    status_code = 400
    code = "idempotency_key_invalid"
    message = "The Idempotency-Key must be 1 to 255 letters, digits or symbols, with no spaces."


class IdempotencyKeyReusedError(AppError):
    status_code = 422
    code = "idempotency_key_reused"
    message = "This Idempotency-Key was already used for a different request. Send a new key."


class IdempotencyKeyInProgressError(ConflictError):
    code = "idempotency_key_in_progress"
    message = "A request with this Idempotency-Key is still running. Try again in a moment."
