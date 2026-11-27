"""Errors from the passports app. Every message is written for the person who sees it."""

from apps.platform.core.exceptions import AppError


class PieceNotAuthenticError(AppError):
    code = "piece_not_verified"
    message = "Only a piece we have verified as authentic gets a passport."
