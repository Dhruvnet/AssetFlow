from rest_framework import serializers


class CheckOutReturnSerializer(serializers.Serializer):
    condition_note = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
    )

    needs_maintenance = serializers.BooleanField(
        required=False,
        default=False,
    )