"""The order confirmation email (build E21).

Sent once per order, after the payment that makes it ``paid`` is saved
(``transaction.on_commit``), so an email never goes out for a change that was rolled
back. ``confirmation_sent_at`` is claimed before sending and released if the send
fails, so a repeated Stripe notice cannot send it twice, and a mail outage leaves the
order ready for ``python manage.py send_order_confirmations``. A failed send is
logged; it never touches the payment.
"""

import logging
from typing import Any

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

from apps.shop.orders.enums import OrderStatus
from apps.shop.orders.models import Order

logger = logging.getLogger(__name__)


def deliver(message: EmailMultiAlternatives) -> None:
    """Hand the message to the mailer (Resend on the live site). Tests replace this."""
    message.send()


def render_confirmation(order: Order) -> tuple[str, str, str]:
    """Subject, plain text and HTML of an order's confirmation."""
    context: dict[str, Any] = {
        "order": order,
        "piece": order.piece,
        "first_name": order.buyer.first_name,
        "item": order.money(order.item_minor),
        "tax": order.money(order.tax_minor) if order.tax_minor else None,
        "total": order.money(order.total_minor),
        "order_url": settings.ORDER_PAGE_URL.format(
            order_id=order.pk, order_number=order.order_number
        ),
        "company": settings.COMPANY_LEGAL_NAME,
        "support_email": settings.SUPPORT_EMAIL,
    }
    subject = f"Your Samwab order {order.order_number} is confirmed"
    return (
        subject,
        render_to_string("orders/confirmation.txt", context),
        render_to_string("orders/confirmation.html", context),
    )


def send_confirmation(order_id: Any) -> bool:
    """Send the confirmation if the order is paid and it has not gone yet.

    Returns True when this call sent it.
    """
    claimed = Order.objects.filter(
        pk=order_id, status=OrderStatus.PAID, confirmation_sent_at__isnull=True
    ).update(confirmation_sent_at=timezone.now())
    if not claimed:
        return False
    order = Order.objects.select_related("buyer", "piece").get(pk=order_id)
    subject, text, html = render_confirmation(order)
    message = EmailMultiAlternatives(
        subject,
        text,
        settings.DEFAULT_FROM_EMAIL,
        [order.buyer.email],
        reply_to=[settings.SUPPORT_EMAIL] if settings.SUPPORT_EMAIL else None,
    )
    message.attach_alternative(html, "text/html")
    try:
        deliver(message)
    except Exception:  # a mail outage must never undo a payment; it is logged loudly
        logger.exception(
            "order %s: could not send the confirmation email; run send_order_confirmations later",
            order.order_number,
        )
        Order.objects.filter(pk=order_id).update(confirmation_sent_at=None)
        return False
    return True


def unsent_confirmations() -> Any:
    """Paid orders whose confirmation has not gone out (oldest first)."""
    return Order.objects.filter(
        status=OrderStatus.PAID, confirmation_sent_at__isnull=True
    ).order_by("paid_at", "id")
