from apps.platform.core.exceptions import AppError


class InvalidLinkError(AppError):
    status_code = 400
    code = "invalid_link"
    message = "This link is not valid or has expired. Join the list again for a new one."
