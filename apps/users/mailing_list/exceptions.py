from apps.platform.core.exceptions import AppError


class InvalidLinkError(AppError):
    status_code = 400
    code = "invalid_link"
    message = (
        "This link has expired or has already been used. Please join the list again for a new one."
    )
