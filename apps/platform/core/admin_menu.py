"""The admin site's menu, grouped by task in plain words (build E16).

Each item shows only to people allowed to open it (their role's ``view``
permission), so a role's menu lists exactly its own screens. The Technical group
(audit log, request keys, Stripe events, login emails) is for superusers.

Imported by the settings, so it must not import models: links are lazy.
"""

from collections.abc import Callable
from typing import Any

from django.http import HttpRequest
from django.urls import reverse_lazy

Allowed = Callable[[HttpRequest], bool]


def can_view(app_label: str, model: str) -> Allowed:
    def allowed(request: HttpRequest) -> bool:
        user = request.user
        return bool(
            user.is_active
            and user.is_staff
            and (
                user.has_perm(f"{app_label}.view_{model}")
                or user.has_perm(f"{app_label}.change_{model}")
            )
        )

    return allowed


def superuser_only(request: HttpRequest) -> bool:
    return bool(request.user.is_superuser)


def item(
    title: str, icon: str, app_label: str, model: str, *, technical: bool = False
) -> dict[str, Any]:
    return {
        "title": title,
        "icon": icon,
        "link": reverse_lazy(f"admin:{app_label}_{model}_changelist"),
        "permission": superuser_only if technical else can_view(app_label, model),
    }


NAVIGATION: list[dict[str, Any]] = [
    {
        "title": "Shop",
        "separator": True,
        "items": [
            {"title": "Home", "icon": "home", "link": reverse_lazy("admin:index")},
            item("Pieces", "diamond", "pieces", "piece"),
            item("Pieces for sale", "sell", "listings", "listing"),
            item("Passports", "badge", "passports", "passport"),
            item("Condition reports", "fact_check", "passports", "conditionreport"),
            item("Restorations", "build", "passports", "restoration"),
        ],
    },
    {
        "title": "Drops and mailing list",
        "separator": True,
        "items": [
            item("Drops", "event", "listings", "drop"),
            item("Mailing list", "mail", "mailing_list", "listmember"),
        ],
    },
    {
        "title": "Orders",
        "separator": True,
        "items": [item("Orders", "shopping_bag", "orders", "order")],
    },
    {
        "title": "Catalog and prices",
        "separator": True,
        "collapsible": True,
        "items": [
            item("Brands", "workspace_premium", "catalog", "brand"),
            item("Designs", "styler", "catalog", "productmodel"),
            item("Categories", "category", "catalog", "category"),
            item("Materials", "texture", "catalog", "material"),
            item("Past sales (price research)", "query_stats", "catalog", "comparablesale"),
            item("Photo checklists", "photo_camera", "catalog", "captureprotocol"),
        ],
    },
    {
        "title": "People",
        "separator": True,
        "collapsible": True,
        "items": [
            item("Accounts", "person", "accounts", "user"),
            item("Legal texts", "gavel", "legal", "legaldocument"),
            item("Terms accepted", "task_alt", "legal", "termsacceptance"),
            item("Consents", "verified_user", "legal", "consent"),
            item("Staff roles", "badge", "auth", "group", technical=True),
        ],
    },
    {
        "title": "Technical",
        "separator": True,
        "collapsible": True,
        "items": [
            item("Audit log", "history", "audit", "auditevent", technical=True),
            item("Saved request keys", "key", "idempotency", "idempotencykey", technical=True),
            item("Stripe events", "receipt_long", "payments", "stripeevent", technical=True),
            item(
                "Login email addresses",
                "alternate_email",
                "account",
                "emailaddress",
                technical=True,
            ),
        ],
    },
]
