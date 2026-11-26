"""The mailing list in the admin site: read-only for the staff who use it."""

from apps.users.accounts import roles
from apps.users.accounts.permissions import Grants

ROLE_PERMISSIONS: Grants = {
    roles.CATALOG_EDITOR: {"listmember": ("view",)},  # drops are emailed to the list
    roles.SUPPORT: {"listmember": ("view",)},
    roles.FINANCE: {"listmember": ("view",)},
}
