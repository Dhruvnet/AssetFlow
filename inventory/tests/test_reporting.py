from datetime import date, timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from inventory.models import Asset, CheckOut, Employee


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def make_asset(db):
    counter = {"value": 0}

    def _make(**kwargs):
        counter["value"] += 1

        defaults = {
            "asset_tag": (
                f"ASSET-{counter['value']:03d}"
            ),
            "name": (
                f"Test Asset {counter['value']}"
            ),
            "category": Asset.Category.LAPTOP,
            "status": Asset.Status.AVAILABLE,
            "purchase_date": (
                date.today() - timedelta(days=100)
            ),
        }

        defaults.update(kwargs)

        return Asset.objects.create(**defaults)

    return _make


@pytest.fixture
def make_employee(db):
    counter = {"value": 0}

    def _make(**kwargs):
        counter["value"] += 1

        defaults = {
            "employee_code": (
                f"EMP{counter['value']:03d}"
            ),
            "full_name": (
                f"Employee {counter['value']}"
            ),
            "email": (
                f"employee{counter['value']}@example.com"
            ),
            "is_active": True,
        }

        defaults.update(kwargs)

        return Employee.objects.create(**defaults)

    return _make


def create_checkout(
    *,
    asset,
    employee,
    due_at,
    checked_out_at,
    returned_at=None,
):
    checkout = CheckOut.objects.create(
        asset=asset,
        employee=employee,
        due_at=due_at,
        returned_at=returned_at,
    )

    CheckOut.objects.filter(
        pk=checkout.pk,
    ).update(
        checked_out_at=checked_out_at,
    )

    checkout.refresh_from_db()

    return checkout


# ============================================================
# Employee summary
# ============================================================


@pytest.mark.django_db
def test_employee_summary_values(
    api_client,
    make_asset,
    make_employee,
):
    fixed_now = timezone.now()

    employee = make_employee(
        employee_code="EMP001",
    )

    # Returned after 2 days.
    create_checkout(
        asset=make_asset(
            asset_tag="ASSET-001",
        ),
        employee=employee,
        checked_out_at=(
            fixed_now - timedelta(days=10)
        ),
        returned_at=(
            fixed_now - timedelta(days=8)
        ),
        due_at=(
            fixed_now - timedelta(days=7)
        ),
    )

    # Returned after 4 days.
    create_checkout(
        asset=make_asset(
            asset_tag="ASSET-002",
        ),
        employee=employee,
        checked_out_at=(
            fixed_now - timedelta(days=8)
        ),
        returned_at=(
            fixed_now - timedelta(days=4)
        ),
        due_at=(
            fixed_now - timedelta(days=3)
        ),
    )

    # Currently held and overdue.
    create_checkout(
        asset=make_asset(
            asset_tag="ASSET-003",
        ),
        employee=employee,
        checked_out_at=(
            fixed_now - timedelta(days=5)
        ),
        due_at=(
            fixed_now - timedelta(days=2)
        ),
    )

    # Currently held but not overdue.
    create_checkout(
        asset=make_asset(
            asset_tag="ASSET-004",
        ),
        employee=employee,
        checked_out_at=(
            fixed_now - timedelta(days=2)
        ),
        due_at=(
            fixed_now + timedelta(days=5)
        ),
    )

    # Due exactly now.
    create_checkout(
        asset=make_asset(
            asset_tag="ASSET-005",
        ),
        employee=employee,
        checked_out_at=(
            fixed_now - timedelta(days=1)
        ),
        due_at=fixed_now,
    )

    with patch(
        "inventory.services.reporting.timezone.now",
        return_value=fixed_now,
    ):
        response = api_client.get(
            "/api/v1/employees/EMP001/summary/"
        )

    assert response.status_code == 200

    assert (
        response.data["lifetime_checkout_count"]
        == 5
    )

    assert (
        response.data["currently_held_count"]
        == 3
    )

    assert (
        response.data["currently_overdue_count"]
        == 1
    )

    # Average of 2 days and 4 days.
    assert (
        response.data["mean_hold_duration_days"]
        == 3.0
    )


@pytest.mark.django_db
def test_employee_summary_missing_employee(
    api_client,
):
    response = api_client.get(
        "/api/v1/employees/UNKNOWN/summary/"
    )

    assert response.status_code == 404


# ============================================================
# Overdue report
# ============================================================


@pytest.mark.django_db
def test_overdue_report(
    api_client,
    make_asset,
    make_employee,
):
    fixed_now = timezone.now()

    employee = make_employee(
        employee_code="EMP001",
        full_name="Jane Doe",
    )

    # 5 days overdue.
    asset_one = make_asset(
        asset_tag="ASSET-001",
        name="Most Overdue Asset",
    )

    create_checkout(
        asset=asset_one,
        employee=employee,
        checked_out_at=(
            fixed_now - timedelta(days=10)
        ),
        due_at=(
            fixed_now - timedelta(days=5)
        ),
    )

    # 2 days overdue.
    asset_two = make_asset(
        asset_tag="ASSET-002",
        name="Less Overdue Asset",
    )

    create_checkout(
        asset=asset_two,
        employee=employee,
        checked_out_at=(
            fixed_now - timedelta(days=5)
        ),
        due_at=(
            fixed_now - timedelta(days=2)
        ),
    )

    # Due exactly now — NOT overdue.
    asset_three = make_asset(
        asset_tag="ASSET-003",
    )

    create_checkout(
        asset=asset_three,
        employee=employee,
        checked_out_at=(
            fixed_now - timedelta(days=2)
        ),
        due_at=fixed_now,
    )

    # Future due date — NOT overdue.
    asset_four = make_asset(
        asset_tag="ASSET-004",
    )

    create_checkout(
        asset=asset_four,
        employee=employee,
        checked_out_at=(
            fixed_now - timedelta(days=1)
        ),
        due_at=(
            fixed_now + timedelta(days=2)
        ),
    )

    # Returned checkout — NOT included.
    asset_five = make_asset(
        asset_tag="ASSET-005",
    )

    create_checkout(
        asset=asset_five,
        employee=employee,
        checked_out_at=(
            fixed_now - timedelta(days=10)
        ),
        due_at=(
            fixed_now - timedelta(days=5)
        ),
        returned_at=(
            fixed_now - timedelta(days=1)
        ),
    )

    with patch(
        "inventory.services.reporting.timezone.now",
        return_value=fixed_now,
    ):
        response = api_client.get(
            "/api/v1/reports/overdue/"
        )

    assert response.status_code == 200

    assert len(response.data) == 2

    # Most overdue first.
    assert (
        response.data[0]["asset_tag"]
        == "ASSET-001"
    )

    assert (
        response.data[0]["days_overdue"]
        == 5
    )

    assert (
        response.data[1]["asset_tag"]
        == "ASSET-002"
    )

    assert (
        response.data[1]["days_overdue"]
        == 2
    )


@pytest.mark.django_db
def test_overdue_report_returns_empty_list(
    api_client,
):
    response = api_client.get(
        "/api/v1/reports/overdue/"
    )

    assert response.status_code == 200
    assert response.data == []