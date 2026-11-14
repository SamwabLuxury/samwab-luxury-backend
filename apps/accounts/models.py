from typing import ClassVar

from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import PermissionsMixin
from django.core.validators import RegexValidator
from django.db import models
from django.db.models.functions import Lower

from apps.accounts.managers import UserManager, normalise_email
from apps.core.models import BaseModel


class User(AbstractBaseUser, PermissionsMixin, BaseModel):
    """One person's account. Buyers, owners, dealers and staff are all users.

    People log in with their email address; there is no username.

    A user's role is not stored here. Being an owner or a dealer is worked out
    from what the person has completed (payout setup, ID check, approval), so
    one account can buy, sell and bid. Staff permissions use Django groups.
    """

    email = models.EmailField(unique=True, max_length=254)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    country = models.CharField(
        max_length=2,
        blank=True,
        validators=[RegexValidator(r"^[A-Z]{2}$", "Use a two-letter country code, such as NG.")],
        help_text="Two-letter country code (ISO 3166-1), such as NG or US.",
    )
    locale = models.CharField(max_length=10, default="en")
    timezone = models.CharField(max_length=64, default="UTC")

    is_active = models.BooleanField(
        default=True, help_text="Untick to block this account without deleting it."
    )
    is_staff = models.BooleanField(default=False, help_text="Can log in to the admin site.")
    is_house_account = models.BooleanField(
        default=False, help_text="Samwab's own account, which owns house stock."
    )
    verification_tier = models.PositiveSmallIntegerField(
        default=0, help_text="How far this person's identity has been checked. 0 means not yet."
    )
    anonymised_at = models.DateTimeField(
        null=True, blank=True, help_text="Set when personal details were removed on request."
    )

    objects: ClassVar[UserManager] = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: ClassVar[list[str]] = []

    class Meta:
        db_table = "users"
        constraints = (
            # Emails are stored in lowercase only. Together with the unique rule on
            # the column, "Ada@x.com" and "ada@x.com" can never be two accounts.
            models.CheckConstraint(
                condition=models.Q(email=Lower("email")), name="users_email_is_lowercase"
            ),
        )

    def __str__(self) -> str:
        return self.email

    def clean(self) -> None:
        """Runs whenever a user is checked before saving (forms, the admin, the manager)."""
        super().clean()
        self.email = normalise_email(self.email)
