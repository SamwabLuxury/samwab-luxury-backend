"""Business-rule errors the catalog services raise. The API layer turns them into responses."""

from apps.core.exceptions import AppError, ConflictError


class ProtocolNotDraftError(ConflictError):
    code = "protocol_not_draft"
    message = "Only a draft protocol can be changed or activated."


class ProtocolNotActiveError(ConflictError):
    code = "protocol_not_active"
    message = "Only an active protocol can be retired."


class ProtocolHasNoShotsError(AppError):
    code = "protocol_has_no_shots"
    message = "A protocol needs at least one required shot before it is used."
