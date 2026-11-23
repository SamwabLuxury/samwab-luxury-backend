from apps.core.exceptions import AppError, ConflictError


class ListingNotReadyError(AppError):
    """Publishing was refused: the message lists everything still missing. HTTP 422."""

    code = "listing_not_ready"
    message = "This listing is not ready to publish."


class PieceAlreadyListedError(ConflictError):
    code = "piece_already_listed"
    message = "This piece already has an open listing. Withdraw it first."


class ListingClosedError(ConflictError):
    code = "listing_closed"
    message = "This listing is closed; its price can no longer change."


class ListingHeldError(ConflictError):
    code = "listing_held"
    message = "A buyer is paying for this piece right now. Try again after their 15-minute hold."
