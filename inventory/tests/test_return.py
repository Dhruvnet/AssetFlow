from datetime import date, timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from inventory.models import Asset, CheckOut, Employee

@pytest.fixture
def checked_out_asset(db):
    asset = Asset.objects.create(
        asset_tag="LAPTOP-RETURN-001",
        name="Dell XPS 15",
        category=Asset.Category.LAPTOP,
        status=Asset.Status.CHECKED_OUT,
        purchase_date=date.today() - timedelta(days=100),
    )

    employee = Employee.objects.create(
        employee_code="EMP-RETURN-001",
        full_name="Jane Doe",
        email="jane.return@example.com",
        is_active=True,
    )

    checkout = CheckOut.objects.create(
        asset=asset,
        employee=employee,
        due_at=timezone.now() + timedelta(days=7),
        condition_note="Issued in good condition.",
    )

    return asset, employee, checkout


# ============================================================
# Normal return
# ============================================================


@pytest.mark.django_db
def test_return_asset_success(
    api_client,
    checked_out_asset,
):
    asset, employee, checkout = checked_out_asset

    response = api_client.post(
        f"/api/v1/checkouts/{checkout.id}/return/",
        {
            "condition_note": (
                "Returned in good condition."
            ),
            "needs_maintenance": False,
        },
        format="json",
    )

    assert response.status_code == 200

    checkout.refresh_from_db()
    asset.refresh_from_db()

    assert checkout.returned_at is not None

    assert checkout.condition_note == (
        "Returned in good condition."
    )

    assert asset.status == Asset.Status.AVAILABLE

    assert response.data["message"] == (
        "Asset returned successfully."
    )


# ============================================================
# Maintenance return
# ============================================================


@pytest.mark.django_db
def test_return_asset_to_maintenance(
    api_client,
    checked_out_asset,
):
    asset, employee, checkout = checked_out_asset

    response = api_client.post(
        f"/api/v1/checkouts/{checkout.id}/return/",
        {
            "condition_note": (
                "Screen requires repair."
            ),
            "needs_maintenance": True,
        },
        format="json",
    )

    assert response.status_code == 200

    checkout.refresh_from_db()
    asset.refresh_from_db()

    assert checkout.returned_at is not None

    assert checkout.condition_note == (
        "Screen requires repair."
    )

    assert asset.status == Asset.Status.MAINTENANCE


# ============================================================
# Duplicate return
# ============================================================


@pytest.mark.django_db
def test_return_already_returned_checkout_rejected(
    api_client,
    checked_out_asset,
):
    asset, employee, checkout = checked_out_asset

    first_response = api_client.post(
        f"/api/v1/checkouts/{checkout.id}/return/",
        {
            "condition_note": (
                "Returned successfully."
            ),
            "needs_maintenance": False,
        },
        format="json",
    )

    assert first_response.status_code == 200

    second_response = api_client.post(
        f"/api/v1/checkouts/{checkout.id}/return/",
        {
            "condition_note": (
                "Trying to return again."
            ),
            "needs_maintenance": True,
        },
        format="json",
    )

    assert second_response.status_code == 409

    checkout.refresh_from_db()
    asset.refresh_from_db()

    assert asset.status == Asset.Status.AVAILABLE


# ============================================================
# Unknown checkout
# ============================================================


@pytest.mark.django_db
def test_return_missing_checkout(
    api_client,
):
    response = api_client.post(
        "/api/v1/checkouts/99999/return/",
        {
            "condition_note": "Returned.",
            "needs_maintenance": False,
        },
        format="json",
    )

    assert response.status_code == 404