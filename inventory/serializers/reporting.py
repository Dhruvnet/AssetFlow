from rest_framework import serializers


class EmployeeSummarySerializer(serializers.Serializer):
    employee_code = serializers.CharField()

    lifetime_checkout_count = serializers.IntegerField()

    currently_held_count = serializers.IntegerField()

    currently_overdue_count = serializers.IntegerField()

    mean_hold_duration_days = serializers.FloatField(
        allow_null=True,
    )


class EmployeeCheckOutSerializer(serializers.Serializer):
    id = serializers.IntegerField()

    asset_name = serializers.CharField()

    asset_tag = serializers.CharField()

    checked_out_at = serializers.DateTimeField()

    due_at = serializers.DateTimeField()

    returned_at = serializers.DateTimeField(
        allow_null=True,
    )

    status = serializers.CharField()


class EmployeeCheckOutHistorySerializer(
    serializers.Serializer
):
    employee_code = serializers.CharField()

    checkouts = EmployeeCheckOutSerializer(
        many=True,
    )

class OverdueCheckOutSerializer(serializers.Serializer):
    asset_name = serializers.CharField()

    asset_tag = serializers.CharField()

    employee_code = serializers.CharField()

    employee_name = serializers.CharField()

    days_overdue = serializers.IntegerField()