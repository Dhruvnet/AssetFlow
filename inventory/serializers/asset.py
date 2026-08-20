from rest_framework import serializers

from inventory.models import Asset, CheckOut


class CurrentHolderSerializer(serializers.Serializer):
    """Read-only representation of the employee currently holding an asset."""

    employee_code = serializers.CharField()
    full_name = serializers.CharField()


class AssetCreateSerializer(serializers.ModelSerializer):
    """Used for POST /assets/. Only accepts fields the caller should set."""

    class Meta:
        model = Asset
        fields = [
            "id",
            "asset_tag",
            "name",
            "category",
            "purchase_date",
        ]
        read_only_fields = ["id"]

    def validate_asset_tag(self, value):
        if Asset.objects.filter(asset_tag=value).exists():
            raise serializers.ValidationError("Asset tag already exists.")
        return value


class AssetListSerializer(serializers.ModelSerializer):
    """Lightweight representation for GET /assets/ list view."""

    class Meta:
        model = Asset
        fields = [
            "id",
            "asset_tag",
            "name",
            "category",
            "status",
            "purchase_date",
        ]


class AssetDetailSerializer(serializers.ModelSerializer):
    """Full representation for GET /assets/{id}/ including current_holder."""

    current_holder = serializers.SerializerMethodField()

    class Meta:
        model = Asset
        fields = [
            "id",
            "asset_tag",
            "name",
            "category",
            "status",
            "purchase_date",
            "created_at",
            "updated_at",
            "current_holder",
        ]

    def get_current_holder(self, obj):
        open_checkout = (
            CheckOut.objects.filter(asset=obj, returned_at__isnull=True)
            .select_related("employee")
            .first()
        )
        if open_checkout is None:
            return None
        return CurrentHolderSerializer(open_checkout.employee).data