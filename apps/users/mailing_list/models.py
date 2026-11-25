"""One row per email address that asked to join the mailing list.

Only ``confirmed`` members are on the list (double opt-in). ``confirmed_at`` is the
moment of consent. Rows are kept after unsubscribing, so the address is never
emailed again by mistake and the consent history stays.
"""

from django.db import models

from apps.platform.core.models import BaseModel


class MemberStatus(models.TextChoices):
    PENDING = "pending", "Waiting for confirmation"
    CONFIRMED = "confirmed", "On the list"
    UNSUBSCRIBED = "unsubscribed", "Unsubscribed"


class ListMember(BaseModel):
    email = models.EmailField(max_length=254, unique=True, help_text="Stored in lowercase.")
    status = models.CharField(
        max_length=20, choices=MemberStatus.choices, default=MemberStatus.PENDING
    )
    source = models.CharField(
        max_length=40, blank=True, help_text="Where they joined, such as footer."
    )
    confirm_sent_at = models.DateTimeField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True, help_text="When they consented.")
    unsubscribed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "mailing_list_members"
        ordering = ("-id",)
        verbose_name = "list member"
        constraints = (
            models.CheckConstraint(
                condition=models.Q(status__in=MemberStatus.values),
                name="mailing_list_members_status_is_known",
            ),
        )

    def __str__(self) -> str:
        return f"{self.email} ({self.status})"
