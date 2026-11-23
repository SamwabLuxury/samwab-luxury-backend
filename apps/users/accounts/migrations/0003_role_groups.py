"""Create one Django group per role, so admins can give roles in the admin site.

The names are copied here on purpose: a migration must keep working even if
``apps/users/accounts/roles.py`` changes later.
"""

from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

ROLE_NAMES = (
    "owner",
    "dealer",
    "intake_staff",
    "reviewer",
    "catalog_editor",
    "partner",
    "support",
    "finance",
    "admin",
)


def create_role_groups(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    group_model = apps.get_model("auth", "Group")
    for name in ROLE_NAMES:
        group_model.objects.get_or_create(name=name)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_user_signup_intent"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        # Undoing this migration leaves the groups in place, so no one loses a role by accident.
        migrations.RunPython(create_role_groups, migrations.RunPython.noop),
    ]
