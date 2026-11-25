"""The words people see when something goes wrong (build E15).

Every error keeps its ``code`` (the web app decides what to do from it, and codes
never change). This module only chooses the sentence in ``detail`` and in each
field's ``message``: short, polite, no technical words (no "token", "UUID",
"JSON", "null"...). A test checks every error class against ``TECHNICAL_WORDS``.

Field messages: the framework's defaults ("This field may not be null.",
"Must be a valid UUID.") are replaced; a message we wrote ourselves for people
(such as "A drop must close after it opens.") is kept as it is.
"""

import re

GENERAL = {
    "validation_error": "Some details need another look. Please check the highlighted fields.",
    "parse_error": "Something went wrong sending your details. Please try again.",
    "unsupported_media_type": "Something went wrong sending your details. Please try again.",
    "not_authenticated": "Please log in to continue.",
    "authentication_failed": "Please log in to continue.",
    "permission_denied": "Sorry, you don't have access to this.",
    "csrf_failed": "Your session has timed out. Please refresh the page and try again.",
    "not_found": "We couldn't find what you were looking for.",
    "method_not_allowed": "Sorry, that isn't possible here.",
    "not_acceptable": "Something went wrong. Please refresh the page and try again.",
    "throttled": "You've tried that a few times in a row. Please wait a moment and try again.",
    "conflict": "This can't be done right now. Please refresh the page and try again.",
    "illegal_transition": "This can't be done right now. Please refresh the page and try again.",
    "server_error": "Something went wrong on our side. Please try again in a moment.",
    "error": "Something went wrong. Please try again.",
}

# Words that belong to developers, never to shoppers.
TECHNICAL_WORDS = (
    "csrf",
    "token",
    "uuid",
    "json",
    "idempotency",
    " api",
    "endpoint",
    "payload",
    "header",
    "null",
    "boolean",
    "integer",
    " pk",
    "datetime",
    "string",
    "request",
    "http",
    "status",
)

FILL_IN = "Please fill this in."
CHECK_IT = "This doesn't look right. Please check it."

# The framework's own messages that read like developer text, by what they say.
_DEFAULT_INVALID = re.compile(
    r"valid (uuid|integer|boolean|string|number)|wrong format|^not a valid|^invalid pk"
    r"|^incorrect type|^expected a|value out of range|^string value too large"
    r"|^invalid datetime",
    re.IGNORECASE,
)


def _number(message: str) -> str | None:
    found = re.search(r"\d+", message)
    return found.group(0) if found else None


def field_message(code: str, message: str) -> str:
    """The sentence shown under one form field."""
    lowered = message.lower()
    if code in ("required", "blank", "null"):
        return FILL_IN
    if code in ("invalid_choice", "does_not_exist", "incorrect_type"):
        return "Please choose one of the options."
    if code in ("not_a_list", "empty"):
        return "Please choose at least one."
    if code == "unique" or lowered.endswith("already exists."):
        return "This is already in use."
    number = _number(message)
    if code in ("max_digits", "max_decimal_places", "max_whole_digits", "max_string_length"):
        return "Please enter a smaller number."
    if "elements" in lowered and number:
        return (
            f"Please choose no more than {number}."
            if code == "max_length"
            else (f"Please choose at least {number}.")
        )
    if code == "max_length" and number:
        return f"Please keep this to {number} characters or fewer."
    if code == "min_length" and number:
        return f"Please use at least {number} characters."
    if code == "max_value" and number:
        return f"Please enter {number} or less."
    if code == "min_value" and number:
        return f"Please enter {number} or more."
    if "email address" in lowered and lowered.startswith("enter a valid"):
        return "Please enter a valid email address."
    if lowered.startswith("enter a valid url"):
        return "Please enter a full web address, starting with https://."
    if "date" in lowered and ("format" in lowered or "expected a" in lowered):
        return "Please enter a valid date."
    if ("number" in lowered or "integer" in lowered) and _DEFAULT_INVALID.search(message):
        return "Please enter a number."
    if _DEFAULT_INVALID.search(message):
        return CHECK_IT
    return message
