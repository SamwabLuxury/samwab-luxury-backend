from rest_framework import serializers

from apps.users.mailing_list.models import ListMember


class JoinSerializer(serializers.Serializer[None]):
    email = serializers.EmailField(max_length=254)
    source = serializers.CharField(  # type: ignore[assignment]  # named like Field.source
        max_length=40, required=False, allow_blank=True, help_text="Such as footer."
    )


class JoinAnswerSerializer(serializers.Serializer[None]):
    status = serializers.ChoiceField(choices=["check_your_email"])


class TokenSerializer(serializers.Serializer[None]):
    token = serializers.CharField(max_length=500, help_text="From the emailed link.")


class MemberSerializer(serializers.ModelSerializer[ListMember]):
    class Meta:
        model = ListMember
        fields = ("email", "status")
