from apps.core.exceptions import AppError


class PaymentProviderError(AppError):
    """The payment provider refused or could not be reached. HTTP 502.

    The provider's own message is logged, never shown: it can name keys or accounts.
    """

    status_code = 502
    code = "payment_provider_error"
    message = "The payment service could not complete this. Please try again."


class WebhookSignatureError(AppError):
    """A webhook failed the provider's signature check. HTTP 400."""

    status_code = 400
    code = "webhook_signature_invalid"
    message = "The webhook signature could not be verified."
