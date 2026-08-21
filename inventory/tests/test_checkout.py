from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import pytest
from django.db import close_old_connections
from django.utils import timezone
from rest_framework.test import APIClient

from inventory.models import Asset, CheckOut, Employee
from inventory.services.checkout import create_checkout


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def make_asset(db):
    def _make(
        asset_tag="LAPTOP-001",
        status=Asset.Status.AVAILABLE,
        **kwargs,
    ):
        defaults = {
            "name": "Dell XPS 15",
            "category": Asset.Category.LAPTOP,
            "status": status,
            "purchase_date": (
                date.today() - timedelta(days=100)
            ),
        }

        defaults.update(kwargs)

        return Asset.objects.create(
            asset_tag=asset_tag,
            **defaults,
        )

    return _make


@pytest.fixture
def make_employee(db):
    def _make(
        employee_code="EMP001",
        is_active=True,
        **kwargs,
    ):
        defaults = {
            "full_name": "Jane Doe",
            "email": (
                f"{employee_code.lower()}@example.com"
            ),
            "is_active": is_active,
        }

        defaults.update(kwargs)

        return Employee.objects.create(
            employee_code=employee_code,
            **defaults,
        )

    return _make


def checkout_payload(asset, employee, **kwargs):
    payload = {
        "asset_tag": asset.asset_tag,
        "employee_code": employee.employee_code,
        "due_at": (
            timezone.now() + timedelta(days=7)
        ).isoformat(),
        "condition_note": "Issued in good condition.",
    }

    payload.update(kwargs)

    return payload


# ============================================================
# Successful checkout
# ============================================================


@pytest.mark.django_db
def test_create_checkout_success(
    api_client,
    make_asset,
    make_employee,
):
    asset = make_asset()
    employee = make_employee()

    response = api_client.post(
        "/api/v1/checkouts/",
        checkout_payload(asset, employee),
        format="json",
    )

    assert response.status_code == 201

    assert CheckOut.objects.filter(
        asset=asset,
        employee=employee,
        returned_at__isnull=True,
    ).exists()

    assert response.data["data"]["asset_tag"] == (
        asset.asset_tag
    )

    assert response.data["data"]["employee_code"] == (
        employee.employee_code
    )

    asset.refresh_from_db()

    assert asset.status == Asset.Status.CHECKED_OUT


# ============================================================
# Asset validation
# ============================================================


@pytest.mark.django_db
def test_checkout_rejects_already_checked_out_asset(
    api_client,
    make_asset,
    make_employee,
):
    asset = make_asset(
        status=Asset.Status.CHECKED_OUT
    )
    employee = make_employee()

    response = api_client.post(
        "/api/v1/checkouts/",
        checkout_payload(asset, employee),
        format="json",
    )

    assert response.status_code == 400
    assert "asset_tag" in response.data
    assert CheckOut.objects.count() == 0


@pytest.mark.django_db
def test_checkout_rejects_asset_in_maintenance(
    api_client,
    make_asset,
    make_employee,
):
    asset = make_asset(
        status=Asset.Status.MAINTENANCE
    )
    employee = make_employee()

    response = api_client.post(
        "/api/v1/checkouts/",
        checkout_payload(asset, employee),
        format="json",
    )

    assert response.status_code == 400
    assert "asset_tag" in response.data


@pytest.mark.django_db
def test_checkout_rejects_missing_asset(
    api_client,
    make_employee,
):
    employee = make_employee()

    response = api_client.post(
        "/api/v1/checkouts/",
        {
            "asset_tag": "UNKNOWN-ASSET",
            "employee_code": employee.employee_code,
            "due_at": (
                timezone.now() + timedelta(days=7)
            ).isoformat(),
        },
        format="json",
    )

    assert response.status_code == 404
    assert "asset_tag" in response.data


# ============================================================
# Employee validation
# ============================================================


@pytest.mark.django_db
def test_checkout_rejects_inactive_employee(
    api_client,
    make_asset,
    make_employee,
):
    asset = make_asset()

    employee = make_employee(
        is_active=False
    )

    response = api_client.post(
        "/api/v1/checkouts/",
        checkout_payload(asset, employee),
        format="json",
    )

    assert response.status_code == 400
    assert "employee_code" in response.data


@pytest.mark.django_db
def test_checkout_rejects_missing_employee(
    api_client,
    make_asset,
):
    asset = make_asset()

    response = api_client.post(
        "/api/v1/checkouts/",
        {
            "asset_tag": asset.asset_tag,
            "employee_code": "UNKNOWN-EMPLOYEE",
            "due_at": (
                timezone.now() + timedelta(days=7)
            ).isoformat(),
        },
        format="json",
    )

    assert response.status_code == 404
    assert "employee_code" in response.data


# ============================================================
# Due date validation
# ============================================================


@pytest.mark.django_db
def test_checkout_rejects_past_due_date(
    api_client,
    make_asset,
    make_employee,
):
    asset = make_asset()
    employee = make_employee()

    response = api_client.post(
        "/api/v1/checkouts/",
        checkout_payload(
            asset,
            employee,
            due_at=(
                timezone.now() - timedelta(days=1)
            ).isoformat(),
        ),
        format="json",
    )

    assert response.status_code == 400
    assert "due_at" in response.data


@pytest.mark.django_db
def test_checkout_rejects_due_date_more_than_30_days_ahead(
    api_client,
    make_asset,
    make_employee,
):
    asset = make_asset()
    employee = make_employee()

    response = api_client.post(
        "/api/v1/checkouts/",
        checkout_payload(
            asset,
            employee,
            due_at=(
                timezone.now() + timedelta(days=31)
            ).isoformat(),
        ),
        format="json",
    )

    assert response.status_code == 400
    assert "due_at" in response.data


# ============================================================
# Checkout limit
# ============================================================


@pytest.mark.django_db
def test_checkout_rejects_employee_at_limit(
    api_client,
    make_asset,
    make_employee,
):
    employee = make_employee()

    for index in range(3):
        asset = make_asset(
            asset_tag=f"LAPTOP-{index:03d}"
        )

        CheckOut.objects.create(
            asset=asset,
            employee=employee,
            due_at=(
                timezone.now() + timedelta(days=7)
            ),
        )

        asset.status = Asset.Status.CHECKED_OUT
        asset.save()

    new_asset = make_asset(
        asset_tag="LAPTOP-999"
    )

    response = api_client.post(
        "/api/v1/checkouts/",
        checkout_payload(
            new_asset,
            employee,
        ),
        format="json",
    )

    assert response.status_code == 400
    assert "employee_code" in response.data

    new_asset.refresh_from_db()

    assert new_asset.status == Asset.Status.AVAILABLE


# ============================================================
# Atomic behavior
# ============================================================


@pytest.mark.django_db
def test_failed_checkout_does_not_change_asset_status(
    api_client,
    make_asset,
    make_employee,
):
    asset = make_asset(
        status=Asset.Status.MAINTENANCE
    )
    employee = make_employee()

    response = api_client.post(
        "/api/v1/checkouts/",
        checkout_payload(asset, employee),
        format="json",
    )

    assert response.status_code == 400

    asset.refresh_from_db()

    assert asset.status == Asset.Status.MAINTENANCE
    assert CheckOut.objects.count() == 0


# ============================================================
# Concurrency protection
# ============================================================


@pytest.mark.django_db(transaction=True)
def test_concurrent_checkout_only_allows_one():
    asset = Asset.objects.create(
        asset_tag="LAPTOP-CONCURRENT",
        name="Dell XPS 15",
        category=Asset.Category.LAPTOP,
        status=Asset.Status.AVAILABLE,
        purchase_date=(
            date.today() - timedelta(days=100)
        ),
    )

    employee_one = Employee.objects.create(
        employee_code="EMP001",
        full_name="Jane Doe",
        email="jane@example.com",
    )

    employee_two = Employee.objects.create(
        employee_code="EMP002",
        full_name="John Doe",
        email="john@example.com",
    )

    due_at = timezone.now() + timedelta(days=7)

    def attempt_checkout(employee_code):
        close_old_connections()

        try:
            checkout = create_checkout(
                asset_tag=asset.asset_tag,
                employee_code=employee_code,
                due_at=due_at,
            )

            return checkout.id

        except Exception:
            return None

        finally:
            close_old_connections()

    with ThreadPoolExecutor(
        max_workers=2
    ) as executor:
        results = list(
            executor.map(
                attempt_checkout,
                [
                    employee_one.employee_code,
                    employee_two.employee_code,
                ],
            )
        )

    successful_checkouts = [
        result
        for result in results
        if result is not None
    ]

    assert len(successful_checkouts) == 1

    assert CheckOut.objects.filter(
        asset=asset,
        returned_at__isnull=True,
    ).count() == 1

    asset.refresh_from_db()

    assert asset.status == Asset.Status.CHECKED_OUT
    
    


# ============================================================
# 30-day due date validation.
# ============================================================


@pytest.mark.django_db
def test_checkout_rejects_due_date_more_than_30_days_ahead(
    api_client,
    make_asset,
    make_employee,
):
    asset = make_asset()
    employee = make_employee()

    response = api_client.post(
        "/api/v1/checkouts/",
        checkout_payload(
            asset,
            employee,
            due_at=(
                timezone.now() + timedelta(days=31)
            ).isoformat(),
        ),
        format="json",
    )

    assert response.status_code == 400
    assert "due_at" in response.data