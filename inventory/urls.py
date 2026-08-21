from django.urls import path

from inventory.views import (
    AssetDetailView,
    AssetListCreateView,
    CheckOutCreateView,
    CheckOutReturnView,
)

urlpatterns = [
    path("assets/",AssetListCreateView.as_view(),name="asset-list-create",),
    path("assets/<int:pk>/",AssetDetailView.as_view(),name="asset-detail",),
    path("checkouts/",CheckOutCreateView.as_view(),name="checkout-create",),
    path("checkouts/<int:checkout_id>/return/",CheckOutReturnView.as_view(),name="checkout-return",
),
]