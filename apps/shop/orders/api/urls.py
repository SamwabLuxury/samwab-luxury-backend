from django.urls import path

from apps.shop.orders.api.views import OrderCancelView, OrderDetailView, OrderListView

app_name = "orders"

urlpatterns = [
    path("orders/", OrderListView.as_view(), name="list"),
    path("orders/<uuid:id>/", OrderDetailView.as_view(), name="detail"),
    path("orders/<uuid:id>/cancel/", OrderCancelView.as_view(), name="cancel"),
]
