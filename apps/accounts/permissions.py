"""Give each staff role (a Django group) the admin permissions written in code.

Each app lists what each role may do with its own models, in
``apps/<app>/permissions.py``, and connects ``connect_role_permissions`` in its
``AppConfig.ready()``. After every ``migrate`` the groups are set to match, for
that app's models only. So the code, reviewed in a pull request, is the one
place a role's permissions are decided: a change made by hand to a role group in
the admin site is undone by the next ``migrate``.

A grant looks like::

    ROLE_PERMISSIONS = {
        roles.CATALOG_EDITOR: {"brand": ("add", "change", "view")},
    }
"""

from collections.abc import Mapping
from typing import Any

from django.apps import AppConfig
from django.apps import apps as global_apps
from django.apps.registry import Apps
from django.contrib.auth.management import create_permissions
from django.db import DEFAULT_DB_ALIAS
from django.db.models.signals import post_migrate

from apps.accounts.roles import ALL_ROLES

Grants = Mapping[str, Mapping[str, tuple[str, ...]]]


def sync_role_permissions(
    app_config: AppConfig,
    grants: Grants,
    *,
    apps: Apps = global_apps,
    using: str = DEFAULT_DB_ALIAS,
) -> None:
    """Set every role group's permissions on this app's models to exactly ``grants``."""
    unknown = set(grants) - set(ALL_ROLES)
    if unknown:
        raise ValueError(f"Unknown roles: {', '.join(sorted(unknown))}")

    # Django creates permissions on the same signal; make sure they exist before we use them.
    create_permissions(app_config, verbosity=0, apps=apps, using=using)
    group_model = apps.get_model("auth", "Group")
    permission_model = apps.get_model("auth", "Permission")
    app_label = app_config.label
    in_app = permission_model.objects.using(using).filter(content_type__app_label=app_label)
    by_code = {permission.codename: permission for permission in in_app}

    for role in ALL_ROLES:
        wanted = set()
        for model, verbs in grants.get(role, {}).items():
            for verb in verbs:
                code = f"{verb}_{model}"
                if code not in by_code:
                    raise ValueError(f"No permission {app_label}.{code}")
                wanted.add(by_code[code])
        group, _ = group_model.objects.using(using).get_or_create(name=role)
        held = set(group.permissions.filter(content_type__app_label=app_label))
        group.permissions.remove(*(held - wanted))
        group.permissions.add(*(wanted - held))


def connect_role_permissions(app_config: AppConfig, grants: Grants) -> None:
    """Call from ``AppConfig.ready()``: re-apply ``grants`` after every ``migrate``."""

    def after_migrate(sender: AppConfig, **kwargs: Any) -> None:
        sync_role_permissions(
            sender,
            grants,
            apps=kwargs.get("apps", global_apps),
            using=kwargs.get("using", DEFAULT_DB_ALIAS),
        )

    post_migrate.connect(after_migrate, sender=app_config, weak=False)
