"""The allowed order status moves. Services check these before any change.

This build: waiting for payment -> paid or cancelled; a cancelled order whose
money arrived anyway -> refunded. Later builds add the vault and delivery moves.
"""

from apps.platform.core.state_machine import StateMachine
from apps.shop.orders.enums import OrderStatus as S

ORDER = StateMachine(
    "order",
    {
        S.PENDING_PAYMENT: {S.PAID, S.CANCELLED},
        S.CANCELLED: {S.REFUNDED},
    },
)
