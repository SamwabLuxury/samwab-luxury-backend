"""Errors for the Idempotency-Key header. Status codes follow the IETF draft
"The Idempotency-Key HTTP Header Field" (draft-ietf-httpapi-idempotency-key-header).
"""

from apps.platform.core.exceptions import AppError, ConflictError


class IdempotencyKeyMissingError(AppError):
    status_code = 400
    code = "idempotency_key_missing"
    message = "Something went wrong sending your order. Please refresh the page and try again."


class IdempotencyKeyInvalidError(AppError):
    status_code = 400
    code = "idempotency_key_invalid"
    message = "Something went wrong sending your order. Please refresh the page and try again."


class IdempotencyKeyReusedError(AppError):
    status_code = 422
    code = "idempotency_key_reused"
    message = "Something went wrong sending your order. Please refresh the page and try again."


class IdempotencyKeyInProgressError(ConflictError):
    code = "idempotency_key_in_progress"
    message = "We're still working on your last step. Please wait a moment."
