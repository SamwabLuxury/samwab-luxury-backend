"""The allowed status moves for a piece. Services check these before any change.

Custody follows the path in the data model: with_owner, in_transit, at_intake,
in_vault, in_transit, with_buyer. Returns and moves between vaults will add
moves here when their builds settle the rules.
"""

from apps.inventory.pieces.enums import CustodyStatus as C
from apps.inventory.pieces.enums import VerificationStatus as V
from apps.platform.core.state_machine import StateMachine

CUSTODY = StateMachine(
    "piece's custody",
    {
        C.WITH_OWNER: {C.IN_TRANSIT},  # the owner ships it with Samwab's prepaid label
        C.IN_TRANSIT: {C.AT_INTAKE, C.WITH_BUYER},  # reaches the vault, or reaches the buyer
        C.AT_INTAKE: {C.IN_VAULT},  # received and checked, then shelved
        C.IN_VAULT: {C.IN_TRANSIT},  # the buyer's courier collects it
    },
)

VERIFICATION = StateMachine(
    "piece's verification",
    {V.UNVERIFIED: {V.VERIFIED, V.NOT_AUTHENTIC}},
)
