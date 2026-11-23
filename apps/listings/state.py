"""The allowed status moves for a listing. Services check these before any change.

This build uses the moves staff need for house stock. Orders (build E5) add
live to sold; standing bids add matched; expiry comes with price reviews.
"""

from apps.core.state_machine import StateMachine
from apps.listings.enums import ListingStatus as S

LISTING = StateMachine(
    "listing",
    {
        S.DRAFT: {S.LIVE, S.WITHDRAWN},
        S.LIVE: {S.WITHDRAWN},
    },
)
