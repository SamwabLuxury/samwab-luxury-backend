from apps.platform.core.exceptions import AppError


class AddressLimitError(AppError):
    """HTTP 422."""

    code = "address_limit_reached"
    message = "You have reached the most addresses an account can keep."
