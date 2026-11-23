from django.db import models


class OrderStatus(models.TextChoices):
    """The contract's order statuses (S0 board). This build uses the first four moves."""

    PENDING_PAYMENT = "pending_payment", "Waiting for payment"
    RESERVED = "reserved", "Reserved"
    PAID = "paid", "Paid"
    AWAITING_INTAKE = "awaiting_intake", "Awaiting intake"
    AUTHENTICATING = "authenticating", "Authenticating"
    VERIFIED = "verified", "Verified"
    BUYER_DECIDING = "buyer_deciding", "Buyer deciding"
    STORED = "stored", "Stored"
    SHIPPED = "shipped", "Shipped"
    DELIVERED = "delivered", "Delivered"
    BUYER_CONFIRMING = "buyer_confirming", "Buyer confirming"
    RETURN_REQUESTED = "return_requested", "Return requested"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"
    REFUNDED = "refunded", "Refunded"
    RETURNED = "returned", "Returned"


class OrderKind(models.TextChoices):
    HOUSE_SALE = "house_sale", "House sale"
    CONSIGNMENT_SALE = "consignment_sale", "Consignment sale"
    VAULT_TRADE = "vault_trade", "Vault trade"


class Channel(models.TextChoices):
    BUY_NOW = "buy_now", "Buy now"
    BID = "bid", "Bid"
    EBAY = "ebay", "eBay"


class DeliveryChoice(models.TextChoices):
    BUYER_COURIER = "buyer_courier", "The buyer's courier collects it"
    KEEP_IN_VAULT = "keep_in_vault", "Keep it in the vault"


class CancelReason(models.TextChoices):
    BUYER_CANCELLED = "buyer_cancelled", "The buyer cancelled"
    HOLD_EXPIRED = "hold_expired", "Not paid in time"
    LISTING_UNAVAILABLE = "listing_unavailable", "The listing closed before payment arrived"
