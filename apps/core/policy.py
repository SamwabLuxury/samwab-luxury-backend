"""Business time limits and default rates, kept in one place.

Services read these when they create an order and copy the resulting deadline
onto the order. Changing a value here affects new orders only; orders that
already exist keep the deadline they were given.

The client has not confirmed these numbers as final. Change them here and
nowhere else.
"""

from datetime import timedelta
from typing import Final

# How long a reservation deposit holds a piece before the rest must be paid.
RESERVATION_WINDOW: Final = timedelta(minutes=60)

# How long a buyer has to ask for a return, counted from when she confirms receipt.
RETURN_WINDOW: Final = timedelta(hours=24)

# How long the money from a vault trade is held before the seller is paid.
VAULT_TRADE_HOLDING_PERIOD: Final = timedelta(days=7)

# The reservation deposit as a share of the price, in basis points (5,000 = 50%).
# Staff can set a different rate on a fee schedule; this is the starting value.
DEFAULT_RESERVATION_DEPOSIT_BPS: Final = 5_000
