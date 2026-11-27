"""Reads about legal texts, acceptances and consents. Nothing here changes data."""

from collections.abc import Iterable

from django.db.models import Q, QuerySet

from apps.users.accounts.models import User
from apps.users.legal.enums import ConsentKind
from apps.users.legal.models import Consent, LegalDocument

IN_FORCE = Q(effective_at__isnull=False, retired_at__isnull=True)


def texts_in_force() -> QuerySet[LegalDocument]:
    """Every text people can read and accept now: one per kind at most."""
    return LegalDocument.objects.filter(IN_FORCE).order_by("kind")


def in_force(kind: str) -> LegalDocument | None:
    """The version of ``kind`` in force now, or ``None`` while there is none."""
    return texts_in_force().filter(kind=kind).first()


def accepted_ids(user: User) -> set[object]:
    """The texts (by id) this account has accepted for itself, not for one order."""
    return set(
        user.terms_acceptances.filter(order__isnull=True).values_list(
            "legal_document_id", flat=True
        )
    )


def missing(user: User, kinds: Iterable[str]) -> list[LegalDocument]:
    """Texts of these kinds in force now that she has not accepted, in kind order.

    A kind with nothing in force asks for nothing, so publishing a text is what
    switches its requirement on.
    """
    done = accepted_ids(user)
    return [text for text in texts_in_force().filter(kind__in=list(kinds)) if text.pk not in done]


def has_accepted_current(user: User, kind: str) -> bool:
    """Whether she accepted the version of ``kind`` in force. False while none is in force."""
    current = in_force(kind)
    return current is not None and current.pk in accepted_ids(user)


def active_consents(user: User) -> dict[str, Consent | None]:
    """Each consent kind, with her consent in effect now, or ``None``."""
    given = {row.kind: row for row in user.consents.filter(withdrawn_at__isnull=True)}
    return {kind: given.get(kind) for kind in ConsentKind.values}
