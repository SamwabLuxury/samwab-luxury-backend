from typing import Any

from django import forms
from django.conf import settings
from django.contrib.auth.password_validation import UserAttributeSimilarityValidator
from django.core.exceptions import ValidationError
from django.http import HttpRequest

from apps.platform.core.client_ip import get_client_ip
from apps.users.accounts.enums import SignupIntent
from apps.users.accounts.models import User
from apps.users.legal import services as legal


class SignupForm(forms.Form):
    """The fields we add to allauth's sign-up. allauth adds email and password itself.

    The three sign-up pages (buy, sell, dealers) all send this one form; only
    ``intent`` differs. It records which page she used and grants no role.
    ``terms_accepted`` is the "I agree" box: when ticked, the terms of service and
    privacy policy in force are recorded as accepted (build 11).
    """

    intent = forms.ChoiceField(choices=SignupIntent.choices, required=False)
    terms_accepted = forms.BooleanField(required=False)

    def clean_intent(self) -> str:
        intent: str = self.cleaned_data.get("intent") or SignupIntent.BUYER
        return intent

    def clean(self) -> dict[str, Any]:
        """Refuse a password that is too close to the email address.

        allauth's API checks the password without knowing the new user, so
        Django's "too similar to your details" rule never runs. We run it here.
        """
        cleaned_data: dict[str, Any] = super().clean() or {}
        password = cleaned_data.get("password")
        email = cleaned_data.get("email")
        if password and email:
            try:
                UserAttributeSimilarityValidator().validate(password, User(email=email))
            except ValidationError as error:
                self.add_error("password", error)
        return cleaned_data

    def signup(self, request: HttpRequest, user: User) -> None:
        """allauth calls this after it has saved the new user."""
        user.signup_intent = self.cleaned_data["intent"]
        user.save(update_fields=["signup_intent", "updated_at"])
        if self.cleaned_data.get("terms_accepted"):
            legal.accept_in_force(
                user,
                settings.LEGAL_SIGNUP_DOCUMENTS,
                ip_address=get_client_ip(),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
