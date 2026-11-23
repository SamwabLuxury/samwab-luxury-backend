from uuid import UUID

from django.db.models import Prefetch, Q, QuerySet

from apps.accounts.models import User
from apps.orders.models import Order
from apps.pieces.models import Media


def orders_of(user: User, *, role: str = "buyer", status: str = "") -> QuerySet[Order]:
    """A person's orders as buyer (default) or seller, newest first."""
    orders = (
        Order.objects.filter(seller=user) if role == "seller" else Order.objects.filter(buyer=user)
    )
    if status:
        orders = orders.filter(status=status)
    return _with_details(orders)


def order_for(user: User, order_id: UUID | str) -> Order | None:
    """One order the person bought or sold; None for anyone else."""
    found = Order.objects.filter(Q(buyer=user) | Q(seller=user), pk=order_id)
    return _with_details(found).first()


def _with_details(orders: QuerySet[Order]) -> QuerySet[Order]:
    return orders.select_related(
        "piece__brand", "piece__category", "piece__product_model"
    ).prefetch_related(
        Prefetch("piece__photos", queryset=Media.objects.order_by("sort_order", "id")),
        "payments__refunds",
    )
