"""Joining, confirming and leaving the mailing list."""

import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from apps.users.mailing_list import tokens
from apps.users.mailing_list.exceptions import InvalidLinkError
from apps.users.mailing_list.models import ListMember, MemberStatus

logger = logging.getLogger(__name__)

RESEND_AFTER = timedelta(minutes=10)


def join(email: str, *, source: str = "") -> None:
    """Ask to join. Sends a confirmation unless already confirmed or sent < 10 min ago.

    Says nothing about the address's state, so the caller answers the same every time.
    """
    email = email.strip().lower()
    with transaction.atomic():
        member, _ = ListMember.objects.select_for_update().get_or_create(
            email=email, defaults={"source": source}
        )
        if member.status == MemberStatus.CONFIRMED:
            return
        recently = member.confirm_sent_at and timezone.now() - member.confirm_sent_at < RESEND_AFTER
        if recently:
            return
        member.status = MemberStatus.PENDING
        member.unsubscribed_at = None
        member.confirm_sent_at = timezone.now()
        member.save(update_fields=["status", "unsubscribed_at", "confirm_sent_at", "updated_at"])
    if not _send_confirmation(email):
        ListMember.objects.filter(pk=member.pk).update(confirm_sent_at=None)


def _send_confirmation(email: str) -> bool:
    links = {
        "confirm_url": settings.MAILING_LIST_CONFIRM_URL.format(token=tokens.confirm_token(email)),
        "unsubscribe_url": settings.MAILING_LIST_UNSUBSCRIBE_URL.format(
            token=tokens.unsubscribe_token(email)
        ),
        "days": settings.MAILING_LIST_CONFIRM_DAYS,
    }
    try:
        send_mail(
            "Confirm you want the Samwab list",
            render_to_string("mailing_list/confirm.txt", links),
            settings.DEFAULT_FROM_EMAIL,
            [email],
        )
    except Exception:  # a mail outage must not break the form; it is logged loudly
        logger.exception("mailing list: could not send the confirmation email")
        return False
    return True


def confirm(token: str) -> ListMember:
    """Confirm from the emailed link. Confirming twice is fine."""
    try:
        email = tokens.email_from_confirm(token)
    except tokens.BadToken as error:
        raise InvalidLinkError() from error
    with transaction.atomic():
        member = ListMember.objects.select_for_update().filter(email=email).first()
        if member is None or member.status == MemberStatus.UNSUBSCRIBED:
            raise InvalidLinkError()
        if member.status == MemberStatus.PENDING:
            member.status = MemberStatus.CONFIRMED
            member.confirmed_at = timezone.now()
            member.save(update_fields=["status", "confirmed_at", "updated_at"])
    return member


def unsubscribe(token: str) -> ListMember:
    """Leave the list from any email's link. Works for good; repeating is fine."""
    try:
        email = tokens.email_from_unsubscribe(token)
    except tokens.BadToken as error:
        raise InvalidLinkError() from error
    with transaction.atomic():
        member = ListMember.objects.select_for_update().filter(email=email).first()
        if member is None:
            raise InvalidLinkError()
        if member.status != MemberStatus.UNSUBSCRIBED:
            member.status = MemberStatus.UNSUBSCRIBED
            member.unsubscribed_at = timezone.now()
            member.save(update_fields=["status", "unsubscribed_at", "updated_at"])
    return member
