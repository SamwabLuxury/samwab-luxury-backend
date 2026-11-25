from apps.platform.core.exceptions import AppError, ConflictError


class ListingUnavailableError(ConflictError):
    code = "listing_unavailable"
    message = (
        "Sorry, this piece isn't available right now. "
        "It may have sold, or someone else may be checking out."
    )


class OrderNotCancellableError(ConflictError):
    code = "order_not_cancellable"
    message = "This order can no longer be cancelled. If you need help, please contact us."


class OrderAlreadyPaidError(ConflictError):
    code = "order_already_paid"
    message = "Good news: your payment went through, so your order is confirmed."


class ReservationNotAvailableError(AppError):
    code = "reservation_not_available"
    message = "Reserving isn't available. Please pay in full to buy this piece."


class DropNotOpenError(AppError):
    code = "drop_not_open"
    message = (
        "This piece is part of a drop that isn't open to you yet. "
        "Mailing-list members get in first."
    )


class DeliveryChoiceNotAvailableError(AppError):
    code = "delivery_choice_not_available"
    message = "For now, please choose to send your own courier to collect your piece."


class CannotBuyOwnListingError(AppError):
    code = "cannot_buy_own_listing"
    message = "You can't buy a piece you're selling."
