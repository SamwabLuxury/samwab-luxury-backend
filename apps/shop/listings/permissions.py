"""What each staff role may do with listings and drops in the admin site.

Settled by the lead on 26 Nov (build E16): intake staff list house stock; catalog
editors run drops and price adjustments; support and finance (the owners) look.
"""

from apps.users.accounts import roles
from apps.users.accounts.permissions import Grants

_READ = ("view",)

ROLE_PERMISSIONS: Grants = {
    roles.INTAKE_STAFF: {
        "listing": ("add", "change", "view"),
        "listingpricechange": _READ,
        "listingpriceadjustment": ("add", "change", "delete", "view"),
    },
    roles.CATALOG_EDITOR: {
        "listing": ("change", "view"),  # prices and adjustments; intake staff create them
        "listingpricechange": _READ,
        "listingpriceadjustment": ("add", "change", "delete", "view"),
        "drop": ("add", "change", "view"),
        "droplot": ("add", "change", "delete", "view"),
    },
    roles.SUPPORT: {"listing": _READ, "listingpricechange": _READ},
    roles.FINANCE: {
        "listing": _READ,
        "listingpricechange": _READ,
        "listingpriceadjustment": _READ,
        "drop": _READ,
        "droplot": _READ,
    },
}
