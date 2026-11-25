from apps.users.mailing_list.models import ListMember, MemberStatus


def is_member(email: str) -> bool:
    """True when this address confirmed it wants the list and has not left it."""
    return ListMember.objects.filter(
        email=email.strip().lower(), status=MemberStatus.CONFIRMED
    ).exists()
