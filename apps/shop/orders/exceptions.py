from apps.platform.core.exceptions import AppError, ConflictError


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


class DropNotOpenError(AppError):
    code = "drop_not_open"
    message = "This piece is in a drop that is not open to you yet."


class DeliveryChoiceNotAvailableError(AppError):
    code = "delivery_choice_not_available"
    message = "This delivery choice is not available yet. For now, send your own courier."


class CannotBuyOwnListingError(AppError):
    code = "cannot_buy_own_listing"
    message = "You cannot buy your own listing."
