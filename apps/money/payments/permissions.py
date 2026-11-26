"""Payments in the admin site: shown read-only inside an order, for support and finance."""

from apps.users.accounts import roles
from apps.users.accounts.permissions import Grants

ROLE_PERMISSIONS: Grants = {
    roles.SUPPORT: {"payment": ("view",)},
    roles.FINANCE: {"payment": ("view",)},
}
