"""What each staff role may do with the catalog in the admin site.

Applied after every ``migrate`` (see ``apps/users/accounts/permissions.py``). The
contract gives the catalog to ``catalog_editor``: every table in the data
model's catalog group. Brands, categories and designs are retired, never deleted,
so nobody gets ``delete`` on them. Intake staff read the catalog so they can pick
a brand, category, design and materials when they register a piece.

Open with the client (open item 12, staff roles): anything beyond this.
"""

from apps.users.accounts import roles
from apps.users.accounts.permissions import Grants

_EDIT = ("add", "change", "view")
_EDIT_AND_DELETE = ("add", "change", "delete", "view")
_READ = ("view",)

ROLE_PERMISSIONS: Grants = {
    roles.CATALOG_EDITOR: {
        "brand": _EDIT,
        "category": _EDIT,
        "productmodel": _EDIT,
        "material": _EDIT_AND_DELETE,  # no retire column; a material in use cannot be deleted
        "captureprotocol": _EDIT_AND_DELETE,  # drafts only; the admin and service refuse others
        "captureshot": _EDIT_AND_DELETE,  # while the protocol is a draft
        "comparablesale": _EDIT_AND_DELETE,
    },
    roles.INTAKE_STAFF: {
        "brand": _READ,
        "category": _READ,
        "productmodel": _READ,
        "material": _READ,
    },
}
