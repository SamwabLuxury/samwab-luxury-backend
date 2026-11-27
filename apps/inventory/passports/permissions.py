"""What each staff role may do with passports in the admin site.

Applied after every ``migrate`` (see ``apps/users/accounts/permissions.py``).
``reviewer`` decides whether a piece is authentic (the contract gives reviews to that
role), which issues its passport; ``intake_staff`` record condition reports and
restorations and may hide a passport. Passports are issued by code, never added or
deleted by hand.

Open with the owners: may intake staff also verify pieces (open item 12b)?
"""

from apps.users.accounts import roles
from apps.users.accounts.permissions import Grants

ROLE_PERMISSIONS: Grants = {
    roles.REVIEWER: {"passport": ("verify", "view")},
    roles.INTAKE_STAFF: {
        "passport": ("change", "view"),
        "conditionreport": ("add", "view"),
        "restoration": ("add", "change", "view"),
    },
}
