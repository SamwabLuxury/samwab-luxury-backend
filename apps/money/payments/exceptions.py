from apps.platform.core.exceptions import AppError


class PaymentProviderError(AppError):
    """The payment provider refused or could not be reached. HTTP 502.

    The provider's own message is logged, never shown: it can name keys or accounts.
    """

    status_code = 502
    code = "payment_provider_error"
    message = (
        "We couldn't reach our payment provider, so nothing was charged. "
        "Please try again in a moment."
    )


class WebhookSignatureError(AppError):
    """A webhook failed the provider's signature check. HTTP 400."""

    status_code = 400
    code = "webhook_signature_invalid"
    message = "The webhook signature could not be verified."


class TaxAddressError(AppError):
    """Stripe Tax could not place the delivery address (``customer_tax_location_invalid``),
    or there is no address to work tax out from. HTTP 422 (build E22)."""

    code = "tax_address_invalid"
    message = (
        "We couldn't work out sales tax for this address, so nothing was charged. "
        "Please check the state and the ZIP or postal code, then try again."
    )
