"""Writes to orders: placing, cancelling and expiring them, and acting on payments.

Rule: an order's status changes only on our server, from what the payment
provider confirms (``on_payment_update``), never from what the browser says.
Every change locks the order row, re-reads it and checks ``state.py``, so
repeated, late or crossing messages cannot move an order twice or backwards.
"""

import logging
from functools import partial

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.inventory.pieces.enums import VerificationStatus
from apps.money.payments import services as payments
from apps.money.payments.exceptions import PaymentProviderError, TaxAddressError
from apps.money.payments.models import Payment
from apps.money.payments.providers.base import TaxAddress
from apps.platform.audit import services as audit
from apps.platform.core import policy
from apps.platform.core.exceptions import NotFoundError
from apps.shop.listings import drops
from apps.shop.listings import services as listings
from apps.shop.listings.enums import ListingStatus
from apps.shop.listings.models import Listing
from apps.shop.orders import emails
from apps.shop.orders.enums import CancelReason, Channel, OrderKind, OrderStatus
from apps.shop.orders.exceptions import (
    CannotBuyOwnListingError,
    DeliveryChoiceNotAvailableError,
    DropNotOpenError,
    ListingUnavailableError,
    OrderAlreadyPaidError,
    OrderNotCancellableError,
    TermsNotAcceptedError,
)
from apps.shop.orders.models import Order
from apps.shop.orders.numbers import next_order_number
from apps.shop.orders.state import ORDER
from apps.users.accounts.models import User
from apps.users.addresses.models import Address
from apps.users.legal import selectors as legal

logger = logging.getLogger(__name__)


def _address_text(address: Address) -> str:
    lines = [address.recipient_name, address.line1, address.line2 or "", address.city]
    lines += [address.region, address.postal_code, address.country, address.phone or ""]
    return "\n".join(line for line in lines if line)


def _tax_address(address: Address) -> TaxAddress:
    return TaxAddress(
        line1=address.line1,
        line2=address.line2 or "",
        city=address.city,
        state=address.region,
        postal_code=address.postal_code,
        country=address.country,
    )


def _sales_tax(order: Order, address: Address | None) -> tuple[int, str]:
    """Tax on the order's price and the calculation it came from (build E22).

    Nothing while ``SALES_TAX_ENABLED`` is off. Tax follows the delivery address, so
    an order with none cannot be taxed (``TaxAddressError``)."""
    if not settings.SALES_TAX_ENABLED:
        return 0, ""
    if address is None:
        raise TaxAddressError()
    quote = payments.quote_tax(
        order.money(order.item_minor),
        address=_tax_address(address),
        reference=order.order_number,
        key=f"order-{order.pk}-tax",
    )
    return quote.tax.amount_minor, quote.calculation_id


def create_order(
    buyer: User,
    listing: Listing,
    *,
    delivery_choice: str,
    shipping_address: Address | None = None,
    acquisition_source: str = "",
    known_before: bool | None = None,
) -> tuple[Order, str]:
    """Place an order for a live listing and start its one payment.

    Returns the order and the client secret the browser confirms the payment with.
    The listing row is locked, so two buyers cannot both get the piece. If the
    provider cannot be reached, nothing is saved. Only the delivery choices in
    ``DELIVERY_CHOICES_OFFERED`` are accepted. Every text in ``LEGAL_CHECKOUT_DOCUMENTS``
    that is in force must be accepted first (422 ``terms_not_accepted``). With
    ``SALES_TAX_ENABLED``, sales tax from the delivery address is added on top of the
    price; an address Stripe Tax cannot place is 422 ``tax_address_invalid``, and
    nothing is saved.
    """
    if delivery_choice not in settings.DELIVERY_CHOICES_OFFERED:
        raise DeliveryChoiceNotAvailableError()
    if legal.missing(buyer, settings.LEGAL_CHECKOUT_DOCUMENTS):
        raise TermsNotAcceptedError()
    release_expired_hold(listing)
    with transaction.atomic():
        listing = (
            Listing.objects.select_for_update(of=("self",))
            .select_related("piece")
            .get(pk=listing.pk)
        )
        if (
            listing.status != ListingStatus.LIVE
            or listing.piece.verification_status == VerificationStatus.NOT_AUTHENTIC
            or listing.orders.filter(status=OrderStatus.PENDING_PAYMENT).exists()
        ):
            raise ListingUnavailableError()
        if listing.seller_id == buyer.pk:
            raise CannotBuyOwnListingError()
        if not drops.open_to(listing, buyer):
            raise DropNotOpenError()
        item = listing.ask_minor
        order = Order(
            kind=OrderKind.HOUSE_SALE,
            listing=listing,
            piece=listing.piece,
            buyer=buyer,
            seller_id=listing.seller_id,
            channel=Channel.BUY_NOW,
            acquisition_source=acquisition_source,
            known_before=known_before,
            item_minor=item,
            seller_share_minor=item,
            total_minor=item,
            currency=listing.currency,
            delivery_choice=delivery_choice,
            shipping_address=_address_text(shipping_address) if shipping_address else None,
            hold_until=timezone.now() + policy.CHECKOUT_HOLD,
        )
        order.order_number = next_order_number(timezone.now())
        order.tax_minor, order.tax_calculation_id = _sales_tax(order, shipping_address)
        order.total_minor = order.item_minor + order.tax_minor
        order.save()
        _, client_secret = payments.start_payment(
            order=order,
            amount=order.money(order.total_minor),
            reference=order.order_number,
            key=f"order-{order.pk}-full",
            tax_calculation=order.tax_calculation_id,
        )
        audit.record_saved(order, before=None, by=buyer)
    return order, client_secret


def _locked(order: Order) -> Order:
    return Order.objects.select_for_update(of=("self",)).get(pk=order.pk)


def _move(order: Order, to: str, *, verb: str, by: User | None, **fields: object) -> Order:
    was = order.status
    ORDER.check(was, to)
    order.status = to
    for name, value in fields.items():
        setattr(order, name, value)
    order.save()
    audit.record(verb, order, by=by, changes={"status": {"from": was, "to": to}})
    return order


def _close(order: Order, *, reason: str, by: User | None) -> Order:
    """Cancel a waiting order and its payment. If the payment went through meanwhile,
    the order is marked paid instead and returned paid: callers commit that first,
    then report it."""
    payment = order.payments.order_by("-id").first()
    if payment is not None:
        try:
            payments.cancel_payment(payment)
        except PaymentProviderError:
            payments.payment_changed(payment.provider_payment_id, source="cancel")
            order.refresh_from_db()
            if order.status == OrderStatus.PAID:
                return order
            raise
    return _move(
        order,
        OrderStatus.CANCELLED,
        verb="cancelled",
        by=by,
        cancelled_at=timezone.now(),
        cancel_reason=reason,
    )


def cancel_order(order: Order, *, by: User) -> Order:
    """The buyer leaves checkout. Only while waiting for payment (409 otherwise).

    If the payment succeeded at that very moment, the order is saved as paid and
    then ``OrderAlreadyPaidError`` (409) is raised.
    """
    with transaction.atomic():
        current = _locked(order)
        if current.buyer_id != by.pk:
            raise NotFoundError()
        if current.status != OrderStatus.PENDING_PAYMENT:
            raise OrderNotCancellableError()
        closed = _close(current, reason=CancelReason.BUYER_CANCELLED, by=by)
    if closed.status == OrderStatus.PAID:
        raise OrderAlreadyPaidError()
    return closed


def _expire(order: Order) -> None:
    """Close one order whose hold ran out, in its own transaction, so that what
    it learns (even "it was paid after all") is kept."""
    with transaction.atomic():
        current = _locked(order)
        if current.status == OrderStatus.PENDING_PAYMENT and current.hold_until <= timezone.now():
            _close(current, reason=CancelReason.HOLD_EXPIRED, by=None)


def release_expired_hold(listing: Listing) -> None:
    """Free a listing whose checkout hold ran out (checked when the next buyer comes)."""
    for order in listing.orders.filter(
        status=OrderStatus.PENDING_PAYMENT, hold_until__lte=timezone.now()
    ):
        _expire(order)


def expire_stale_orders() -> int:
    """Close every order whose hold ran out. Returns how many were looked at."""
    stale = list(
        Order.objects.filter(status=OrderStatus.PENDING_PAYMENT, hold_until__lte=timezone.now())
    )
    for order in stale:
        _expire(order)
    return len(stale)


def reconcile_pending() -> int:
    """Ask the provider about every payment of an order still waiting (a webhook may
    have been missed). Returns how many were asked about."""
    waiting = Payment.objects.filter(order__status=OrderStatus.PENDING_PAYMENT)
    ids = list(waiting.values_list("provider_payment_id", flat=True))
    for provider_payment_id in ids:
        payments.payment_changed(provider_payment_id, source="reconcile")
    return len(ids)


def on_payment_update(update: payments.PaymentUpdate) -> None:
    """The provider says something about one of our payments. Only "succeeded" acts."""
    seen, payment = update.seen, update.payment
    if seen.status != "succeeded":
        return
    order = Order.objects.select_for_update(of=("self",)).get(pk=payment.order_id)
    expected = order.money(order.total_minor)
    if seen.amount_received != expected:
        logger.error(
            "payment %s: amount received %s, but order %s expects %s; not accepted",
            payment.provider_payment_id,
            seen.amount_received,
            order.order_number,
            expected,
        )
        payment.failure_reason = "amount_mismatch"
        payment.save(update_fields=["failure_reason", "updated_at"])
        return
    if order.status == OrderStatus.PENDING_PAYMENT:
        listing = Listing.objects.select_for_update(of=("self",)).get(pk=order.listing_id)
        if listing.status == ListingStatus.LIVE:
            _move(order, OrderStatus.PAID, verb="paid", by=None, paid_at=timezone.now())
            listings.mark_sold(listing)
            # Email the buyer once the payment is saved, never for a rolled-back one.
            transaction.on_commit(partial(emails.send_confirmation, order.pk))
            return
        _move(
            order,
            OrderStatus.CANCELLED,
            verb="cancelled",
            by=None,
            cancelled_at=timezone.now(),
            cancel_reason=CancelReason.LISTING_UNAVAILABLE,
        )
    if order.status == OrderStatus.CANCELLED:
        # The money came after the order closed: give it back (decision D2) and tell finance.
        payments.refund(payment, reason="missed_deadline")
        _move(order, OrderStatus.REFUNDED, verb="refunded", by=None)
        logger.warning("order %s: payment arrived after it closed; refunded", order.order_number)
