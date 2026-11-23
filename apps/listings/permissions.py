"""What each staff role may do with listings in the admin site.

No role is given listings yet: which staff team prices and lists house stock is
open with the client (open item 12, staff roles). Until then only admins
(superusers) list house stock.
"""

from apps.accounts.permissions import Grants

ROLE_PERMISSIONS: Grants = {}
