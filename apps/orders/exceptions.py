from apps.core.exceptions import AppError, ConflictError


class ListingUnavailableError(ConflictError):
    code = "listing_unavailable"
    message = "This piece is not available: it is sold, withdrawn, or another buyer is paying."


class OrderNotCancellableError(ConflictError):
    code = "order_not_cancellable"
    message = "Only an order waiting for payment can be cancelled."


class OrderAlreadyPaidError(ConflictError):
    code = "order_already_paid"
    message = "The payment went through just now, so this order is paid."


class ReservationNotAvailableError(AppError):
    code = "reservation_not_available"
    message = "Reserving with a deposit is not available yet; pay in full."


class CannotBuyOwnListingError(AppError):
    code = "cannot_buy_own_listing"
    message = "You cannot buy your own listing."
