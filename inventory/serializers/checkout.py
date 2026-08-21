from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from inventory.models import CheckOut


class CheckOutCreateSerializer(serializers.Serializer):
    asset_tag = serializers.CharField(max_length=32)
    employee_code = serializers.CharField(max_length=16)
    due_at = serializers.DateTimeField()
    condition_note = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
    )

    def validate_due_at(self, value):
        now = timezone.now()

        if value <= now:
            raise serializers.ValidationError(
                "Due date must be in the future."
            )

        if value > now + timedelta(days=30):
            raise serializers.ValidationError(
                "Due date cannot be more than 30 days from now."
            )

        return value


class CheckOutSerializer(serializers.ModelSerializer):
    asset_tag = serializers.CharField(
        source="asset.asset_tag",
        read_only=True,
    )

    employee_code = serializers.CharField(
        source="employee.employee_code",
        read_only=True,
    )

    class Meta:
        model = CheckOut

        fields = [
            "id",
            "asset_tag",
            "employee_code",
            "checked_out_at",
            "due_at",
            "returned_at",
            "condition_note",
        ]

        read_only_fields = [
            "id",
            "asset_tag",
            "employee_code",
            "checked_out_at",
            "returned_at",
        ]