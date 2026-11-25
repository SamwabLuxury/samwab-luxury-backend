"""Prove email works: send one test email through Resend to the address given.

Run it after putting RESEND_API_KEY (and DJANGO_DEFAULT_FROM_EMAIL on your verified
domain) in .env or in Render: python manage.py check_email you@example.com
"""

from typing import Any

from django.conf import settings
from django.core.mail import EmailMessage
from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.platform.core.mail import ResendEmailBackend, ResendError


class Command(BaseCommand):
    help = "Send one test email through Resend to the address given."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("to", help="Where to send the test email.")

    def handle(self, *args: Any, **options: Any) -> None:
        if not settings.RESEND_API_KEY:
            raise CommandError("RESEND_API_KEY is not set. Put it in .env (or in Render).")
        message = EmailMessage(
            "Samwab email check",
            "This is a test email from the Samwab backend. If you can read it, email works.",
            settings.DEFAULT_FROM_EMAIL,
            [options["to"]],
        )
        try:
            ResendEmailBackend(api_key=settings.RESEND_API_KEY).send_messages([message])
        except ResendError as failure:
            raise CommandError(
                f"Resend said: {str(failure).rstrip('.')}. Check the key, and that the "
                f"sending address ({settings.DEFAULT_FROM_EMAIL}) is on a domain verified "
                "in Resend."
            ) from failure
        self.stdout.write(
            self.style.SUCCESS(f"Email is working: sent a test email to {options['to']}.")
        )
