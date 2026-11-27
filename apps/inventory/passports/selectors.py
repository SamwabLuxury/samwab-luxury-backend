"""Reads for the public passport page. Nothing here changes data."""

from django.db.models import Prefetch

from apps.inventory.passports.models import ConditionReport, Passport
from apps.inventory.pieces.enums import VerificationStatus
from apps.inventory.pieces.models import Media, Piece


def public_passport(code: str) -> Passport | None:
    """The passport for ``code`` (any letter case), if it is shown to the public.

    A piece later found not authentic has its page taken down here too, whatever its
    passport says.
    """
    return (
        Passport.objects.filter(
            public_code=code.strip().upper(),
            is_public=True,
            piece__verification_status=VerificationStatus.VERIFIED,
        )
        .select_related(
            "piece__brand",
            "piece__category",
            "piece__product_model",
            "piece__current_owner",
        )
        .prefetch_related(
            Prefetch("piece__photos", queryset=Media.objects.order_by("sort_order", "id")),
            Prefetch("piece__condition_reports", queryset=ConditionReport.objects.all()),
            "piece__restorations",
        )
        .first()
    )


def owner_display(piece: Piece) -> str:
    """Who owns it, as the public may see it: Samwab, "Adaeze O." or "Private owner"."""
    owner = piece.current_owner
    if owner.is_house_account:
        return "Samwab"
    first, last = owner.first_name.strip(), owner.last_name.strip()
    if not first:
        return "Private owner"
    return f"{first} {last[0]}." if last else first
