"""python manage.py reset_two_step <email>: turn two-step login off for someone.

For a lost phone and lost recovery codes. Staff set it up again at their next admin
page. On the live site, run it from your machine against Neon (README, "Two-step
login"). It is recorded in the audit log, with no actor.
"""

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.users.accounts import two_step
from apps.users.accounts.models import User


class Command(BaseCommand):
    help = "Turn two-step login off for one account (lost phone and recovery codes)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("email")

    def handle(self, *args: Any, **options: Any) -> None:
        email = options["email"].strip().lower()
        user = User.objects.filter(email=email).first()
        if user is None:
            raise CommandError(f"No account with the email {email}.")
        if two_step.turn_off(user, by=None):
            self.stdout.write(
                f"Two-step login is off for {email}. They set it up again at their next admin page."
            )
        else:
            self.stdout.write(f"{email} had no two-step login. Nothing changed.")
