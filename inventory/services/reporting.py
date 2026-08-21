from django.db.models import (
    Avg,
    Count,
    DurationField,
    ExpressionWrapper,
    F,
    Q,
)
from django.utils import timezone
from rest_framework.exceptions import NotFound

from inventory.models import CheckOut, Employee


def get_employee_summary(*, employee_code):
    now = timezone.now()

    hold_duration = ExpressionWrapper(
        F("checkouts__returned_at")
        - F("checkouts__checked_out_at"),
        output_field=DurationField(),
    )

    summary = (
        Employee.objects
        .filter(employee_code=employee_code)
        .annotate(
            lifetime_checkout_count=Count(
                "checkouts",
            ),
            currently_held_count=Count(
                "checkouts",
                filter=Q(
                    checkouts__returned_at__isnull=True,
                ),
            ),
            currently_overdue_count=Count(
                "checkouts",
                filter=Q(
                    checkouts__returned_at__isnull=True,
                    checkouts__due_at__lt=now,
                ),
            ),
            mean_hold_duration=Avg(
                hold_duration,
                filter=Q(
                    checkouts__returned_at__isnull=False,
                ),
            ),
        )
        .values(
            "employee_code",
            "lifetime_checkout_count",
            "currently_held_count",
            "currently_overdue_count",
            "mean_hold_duration",
        )
        .first()
    )

    if summary is None:
        raise NotFound(
            {
                "detail": "Employee does not exist."
            }
        )

    mean_duration = summary["mean_hold_duration"]

    if mean_duration is None:
        mean_hold_duration_days = None
    else:
        mean_hold_duration_days = (
            mean_duration.total_seconds() / 86400
        )

    return {
        "employee_code": summary["employee_code"],
        "lifetime_checkout_count": (
            summary["lifetime_checkout_count"]
        ),
        "currently_held_count": (
            summary["currently_held_count"]
        ),
        "currently_overdue_count": (
            summary["currently_overdue_count"]
        ),
        "mean_hold_duration_days": (
            round(mean_hold_duration_days, 2)
            if mean_hold_duration_days is not None
            else None
        ),
    }


def get_overdue_checkouts():
    now = timezone.now()

    overdue_duration = ExpressionWrapper(
        now - F("due_at"),
        output_field=DurationField(),
    )

    checkouts = (
        CheckOut.objects
        .filter(
            returned_at__isnull=True,
            due_at__lt=now,
        )
        .select_related(
            "asset",
            "employee",
        )
        .annotate(
            overdue_duration=overdue_duration,
        )
        .order_by("due_at")
    )

    results = []

    for checkout in checkouts:
        results.append(
            {
                "asset_name": checkout.asset.name,
                "asset_tag": checkout.asset.asset_tag,
                "employee_code": (
                    checkout.employee.employee_code
                ),
                "employee_name": (
                    checkout.employee.full_name
                ),
                "days_overdue": (
                    checkout.overdue_duration.days
                ),
            }
        )

    return results


def get_employee_checkouts(*, employee_code):
    employee_exists = Employee.objects.filter(
        employee_code=employee_code,
    ).exists()

    if not employee_exists:
        raise NotFound(
            {
                "detail": "Employee does not exist."
            }
        )

    checkouts = (
        CheckOut.objects
        .filter(
            employee__employee_code=employee_code,
        )
        .select_related(
            "asset",
        )
        .order_by(
            "-checked_out_at",
        )
    )

    results = []

    for checkout in checkouts:
        results.append(
            {
                "id": checkout.id,
                "asset_name": checkout.asset.name,
                "asset_tag": checkout.asset.asset_tag,
                "checked_out_at": checkout.checked_out_at,
                "due_at": checkout.due_at,
                "returned_at": checkout.returned_at,
                "status": (
                    "RETURNED"
                    if checkout.returned_at
                    else "HELD"
                ),
            }
        )

    return {
        "employee_code": employee_code,
        "checkouts": results,
    }


