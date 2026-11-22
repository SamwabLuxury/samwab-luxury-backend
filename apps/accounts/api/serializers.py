import re
from zoneinfo import available_timezones

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.accounts import selectors
from apps.accounts.enums import NextStep
from apps.accounts.models import User
from apps.accounts.roles import ALL_ROLES

LOCALE_PATTERN = re.compile(r"^[a-z]{2}(-[A-Z]{2})?$")


class MeSerializer(serializers.ModelSerializer[User]):
    """The logged-in user, as ``GET`` and ``PATCH /api/v1/me/`` show her.

    She can change her names, country, locale and timezone here. Her email is
    changed through allauth's email endpoints, never here.
    """

    roles = serializers.SerializerMethodField(
        help_text="Every account can buy, so there is no buyer role."
    )
    next_steps = serializers.SerializerMethodField(
        help_text="What she still has to do for her onboarding; empty when nothing is waiting."
    )
    mfa_enabled = serializers.SerializerMethodField(help_text="Whether two-step login is on.")

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "first_name",
            "last_name",
            "country",
            "locale",
            "timezone",
            "roles",
            "signup_intent",
            "next_steps",
            "verification_tier",
            "mfa_enabled",
        )
        read_only_fields = ("id", "email", "signup_intent", "verification_tier")

    @extend_schema_field(serializers.ListField(child=serializers.ChoiceField(ALL_ROLES)))
    def get_roles(self, user: User) -> list[str]:
        return selectors.get_roles(user)

    @extend_schema_field(serializers.ListField(child=serializers.ChoiceField(NextStep.choices)))
    def get_next_steps(self, user: User) -> list[str]:
        return selectors.get_next_steps(user)

    def get_mfa_enabled(self, user: User) -> bool:
        return selectors.has_two_step_login(user)

    def validate_locale(self, value: str) -> str:
        if not LOCALE_PATTERN.match(value):
            raise serializers.ValidationError("Use a language code such as en or en-GB.")
        return value

    def validate_timezone(self, value: str) -> str:
        if value not in available_timezones():
            raise serializers.ValidationError("Use a time zone name such as Africa/Lagos.")
        return value
