"""The links in list emails carry a signed token, so no token is stored.

A confirmation link works for ``MAILING_LIST_CONFIRM_DAYS`` days; an unsubscribe
link works for good (the law and good manners both expect that). Each kind has its
own salt, so one can never be used as the other. Signed with ``SECRET_KEY``.
"""

from django.conf import settings
from django.core import signing

CONFIRM_SALT = "samwab.mailing-list.confirm"
UNSUBSCRIBE_SALT = "samwab.mailing-list.unsubscribe"


class BadToken(Exception):
    """The link is malformed, of the wrong kind, tampered with or expired."""


def confirm_token(email: str) -> str:
    return signing.dumps(email, salt=CONFIRM_SALT, compress=True)


def unsubscribe_token(email: str) -> str:
    return signing.dumps(email, salt=UNSUBSCRIBE_SALT, compress=True)


def email_from_confirm(token: str) -> str:
    max_age = settings.MAILING_LIST_CONFIRM_DAYS * 24 * 60 * 60
    try:
        return str(signing.loads(token, salt=CONFIRM_SALT, max_age=max_age))
    except signing.BadSignature as error:  # SignatureExpired is a BadSignature
        raise BadToken() from error


def email_from_unsubscribe(token: str) -> str:
    try:
        return str(signing.loads(token, salt=UNSUBSCRIBE_SALT))
    except signing.BadSignature as error:
        raise BadToken() from error
