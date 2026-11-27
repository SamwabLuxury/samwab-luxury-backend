"""What each staff role may do with pieces in the admin site.

Applied after every ``migrate`` (see ``apps/users/accounts/permissions.py``). The
contract gives piece intake to ``intake_staff``. Pieces are never deleted, so
nobody gets ``delete_piece``.

Open with the client (open item 12, staff roles): whether ``reviewer`` should
see pieces before review tasks exist (build 29).
"""

from apps.users.accounts import roles
from apps.users.accounts.permissions import Grants

ROLE_PERMISSIONS: Grants = {
    # Reviewers find pieces to verify on the piece list (build 15).
    roles.REVIEWER: {"piece": ("view",)},
    roles.INTAKE_STAFF: {
        "piece": ("add", "change", "view"),
        "piecematerial": ("add", "change", "delete", "view"),
        "media": ("add", "change", "delete", "view"),  # the piece's photos
    },
}
