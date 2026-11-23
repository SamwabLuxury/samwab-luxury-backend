"""The allowed status moves for a listing. Services check these before any change.

Staff publish and withdraw; a paid order (build E5) marks a listing sold.
Standing bids add matched; expiry comes with price reviews.
"""

from apps.core.state_machine import StateMachine
from apps.listings.enums import ListingStatus as S

LISTING = StateMachine(
    "listing",
    {
        S.DRAFT: {S.LIVE, S.WITHDRAWN},
        S.LIVE: {S.WITHDRAWN, S.SOLD},
    },
)
