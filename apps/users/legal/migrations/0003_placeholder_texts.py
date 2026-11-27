"""Placeholder drafts of the terms of service, privacy policy and returns policy.

The owners (or their lawyer) write the real wording. Staff paste it into each draft in
the admin and publish it; a text still marked [PLACEHOLDER cannot be published, and
nothing is asked of anyone until a text is published. The words are written out here
(not imported from the app) so this migration never changes when the app does.
"""

import hashlib

from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

TEXTS = {
    "terms_of_service": "terms of service",
    "privacy_policy": "privacy policy",
    "returns_policy": "returns policy",
}


def _body(name: str) -> str:
    return (
        f"[PLACEHOLDER: Samwab's {name} will appear here.]\n\n"
        "Staff replace this text with the wording from the owners or their lawyer, "
        "then publish it."
    )


def add_drafts(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    document = apps.get_model("legal", "LegalDocument")
    for kind, name in TEXTS.items():
        if document.objects.filter(kind=kind).exists():
            continue
        body = _body(name)
        document.objects.create(
            kind=kind,
            version="1",
            body=body,
            body_sha256=hashlib.sha256(body.encode()).hexdigest(),
        )


def remove_drafts(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    document = apps.get_model("legal", "LegalDocument")
    document.objects.filter(
        kind__in=list(TEXTS), version="1", effective_at__isnull=True, body__startswith="[PLACEHOLDER"
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("legal", "0002_append_only_trigger")]

    operations = [migrations.RunPython(add_drafts, remove_drafts)]
