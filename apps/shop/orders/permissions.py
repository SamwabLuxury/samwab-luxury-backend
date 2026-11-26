"""Orders in the admin site: support (handling orders) and finance (the owners) look.

Nobody edits an order there: orders change only through the buyer and the payment
provider (the screen is read-only for everyone).
"""

from apps.users.accounts import roles
from apps.users.accounts.permissions import Grants

ROLE_PERMISSIONS: Grants = {
    roles.SUPPORT: {"order": ("view",)},
    roles.FINANCE: {"order": ("view",)},
}
