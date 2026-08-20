from django.urls import path

from inventory.views import AssetDetailView, AssetListCreateView

urlpatterns = [
    path("assets/", AssetListCreateView.as_view(), name="asset-list-create"),
    path("assets/<int:pk>/", AssetDetailView.as_view(), name="asset-detail"),
]