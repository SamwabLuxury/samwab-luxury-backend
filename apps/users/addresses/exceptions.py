from apps.platform.core.exceptions import AppError


class AddressLimitError(AppError):
    """HTTP 422."""

    code = "address_limit_reached"
    message = "You can keep up to 20 addresses. Please remove one to add another."
