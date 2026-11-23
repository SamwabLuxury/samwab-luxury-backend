"""Roles a user can hold. Each role is a Django group with the same name.

Every account can buy, so there is no buyer role. The other roles are earned:

- ``owner``: added when Stripe enables her payouts.
- ``dealer``: added when an admin approves her dealer application.
- the staff roles: given by an admin.

Never grant a role because of what someone chose at sign-up. The sign-up
choice (``User.signup_intent``) only decides which onboarding she sees.
"""

from typing import Final

OWNER: Final = "owner"
DEALER: Final = "dealer"
INTAKE_STAFF: Final = "intake_staff"
REVIEWER: Final = "reviewer"
CATALOG_EDITOR: Final = "catalog_editor"
PARTNER: Final = "partner"
SUPPORT: Final = "support"
FINANCE: Final = "finance"
ADMIN: Final = "admin"

# Every role, in the order the API lists them.
ALL_ROLES: Final = (
    OWNER,
    DEALER,
    INTAKE_STAFF,
    REVIEWER,
    CATALOG_EDITOR,
    PARTNER,
    SUPPORT,
    FINANCE,
    ADMIN,
)
