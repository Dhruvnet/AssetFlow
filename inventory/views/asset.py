import django_filters
from rest_framework import filters, generics, status
from rest_framework.response import Response

from inventory.models import Asset
from inventory.pagination import StandardPagination
from inventory.serializers import (
    AssetCreateSerializer,
    AssetDetailSerializer,
    AssetListSerializer,
)


class AssetFilter(django_filters.FilterSet):
    class Meta:
        model = Asset
        fields = ["status", "category"]


class AssetListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/v1/assets/   - paginated, filterable, searchable list
    POST /api/v1/assets/   - create a new asset
    """

    queryset = Asset.objects.all()
    pagination_class = StandardPagination
    filter_backends = [
        django_filters.rest_framework.DjangoFilterBackend,
        filters.SearchFilter,
    ]
    filterset_class = AssetFilter
    search_fields = ["name", "asset_tag"]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return AssetCreateSerializer
        return AssetListSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        asset = serializer.save()

        return Response(
            AssetListSerializer(asset).data,
            status=status.HTTP_201_CREATED,
        )


class AssetDetailView(generics.RetrieveAPIView):
    """
    GET /api/v1/assets/{id}/ - single asset including current_holder
    """

    queryset = Asset.objects.all()
    serializer_class = AssetDetailSerializer