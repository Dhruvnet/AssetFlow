from django.db import transaction
from rest_framework.exceptions import (
    NotFound,
    ValidationError,
)

from inventory.exceptions import Conflict
from inventory.models import Asset, CheckOut, Employee


MAX_OPEN_CHECKOUTS = 3


def create_checkout(
    *,
    asset_tag,
    employee_code,
    due_at,
    condition_note="",
):
    with transaction.atomic():

        # Lock the asset row to prevent two simultaneous
        # checkout requests for the SAME ASSET from succeeding.
        try:
            asset = (
                Asset.objects.select_for_update()
                .get(asset_tag=asset_tag)
            )
        except Asset.DoesNotExist:
            raise NotFound(
                {"asset_tag": "Asset does not exist."}
            )

        try:
            # Lock the employee row too — without this, two concurrent
            # requests for the SAME EMPLOYEE against two DIFFERENT assets
            # can both read open_checkout_count < 3 before either commits,
            # producing 4 open checkouts for one employee (rule 3 violation).
            employee = (
                Employee.objects.select_for_update()
                .get(employee_code=employee_code)
            )
        except Employee.DoesNotExist:
            raise NotFound(
                {"employee_code": "Employee does not exist."}
            )

        if not employee.is_active:
            raise ValidationError(
                {
                    "employee_code": (
                        "Employee is not active."
                    )
                }
            )

        if asset.status != Asset.Status.AVAILABLE:
            raise Conflict(
                {
                    "asset_tag": (
                        "Asset is not available for checkout."
                    )
                }
            )

        open_checkout_count = CheckOut.objects.filter(
            employee=employee,
            returned_at__isnull=True,
        ).count()

        if open_checkout_count >= MAX_OPEN_CHECKOUTS:
            raise Conflict(
                {
                    "employee_code": (
                        f"Employee already has the maximum of "
                        f"{MAX_OPEN_CHECKOUTS} open checkouts."
                    )
                }
            )

        checkout = CheckOut.objects.create(
            asset=asset,
            employee=employee,
            due_at=due_at,
            condition_note=condition_note,
        )

        asset.status = Asset.Status.CHECKED_OUT

        asset.save(
            update_fields=[
                "status",
                "updated_at",
            ]
        )

        return checkout