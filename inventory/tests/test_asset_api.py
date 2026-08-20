from datetime import date, timedelta

import pytest
from rest_framework.test import APIClient

from inventory.models import Asset, CheckOut, Employee


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def make_asset(db):
    def _make(asset_tag="LAPTOP-001", **kwargs):
        defaults = {
            "name": "Dell XPS 15",
            "category": Asset.Category.LAPTOP,
            "purchase_date": date.today() - timedelta(days=100),
        }
        defaults.update(kwargs)
        return Asset.objects.create(asset_tag=asset_tag, **defaults)

    return _make


@pytest.fixture
def make_employee(db):
    def _make(employee_code="EMP001", **kwargs):
        defaults = {
            "full_name": "Jane Doe",
            "email": f"{employee_code.lower()}@example.com",
        }
        defaults.update(kwargs)
        return Employee.objects.create(employee_code=employee_code, **defaults)

    return _make


# ---- Create ----------------------------------------------------------


@pytest.mark.django_db
def test_create_asset_success(api_client):
    payload = {
        "asset_tag": "LAPTOP-999",
        "name": "ThinkPad X1",
        "category": "LAPTOP",
        "purchase_date": "2025-01-01",
    }
    response = api_client.post("/api/v1/assets/", payload, format="json")

    assert response.status_code == 201
    assert response.data["asset_tag"] == "LAPTOP-999"
    assert Asset.objects.filter(asset_tag="LAPTOP-999").exists()


@pytest.mark.django_db
def test_create_asset_duplicate_tag_rejected(api_client, make_asset):
    make_asset(asset_tag="LAPTOP-001")

    payload = {
        "asset_tag": "LAPTOP-001",
        "name": "Duplicate",
        "category": "LAPTOP",
        "purchase_date": "2025-01-01",
    }
    response = api_client.post("/api/v1/assets/", payload, format="json")

    assert response.status_code == 400
    assert "asset_tag" in response.data


@pytest.mark.django_db
def test_create_asset_invalid_category_rejected(api_client):
    payload = {
        "asset_tag": "X-001",
        "name": "Unknown thing",
        "category": "DRONE",  # not a valid choice
        "purchase_date": "2025-01-01",
    }
    response = api_client.post("/api/v1/assets/", payload, format="json")

    assert response.status_code == 400
    assert "category" in response.data


# ---- List / pagination -----------------------------------------------


@pytest.mark.django_db
def test_list_assets_pagination(api_client, make_asset):
    for i in range(25):
        make_asset(asset_tag=f"LAPTOP-{i:03d}")

    response = api_client.get("/api/v1/assets/")

    assert response.status_code == 200
    assert response.data["count"] == 25
    assert len(response.data["results"]) == 20  # page size = 20
    assert response.data["next"] is not None


@pytest.mark.django_db
def test_list_assets_second_page(api_client, make_asset):
    for i in range(25):
        make_asset(asset_tag=f"LAPTOP-{i:03d}")

    response = api_client.get("/api/v1/assets/?page=2")

    assert response.status_code == 200
    assert len(response.data["results"]) == 5


# ---- Filter / search ---------------------------------------------------


@pytest.mark.django_db
def test_filter_assets_by_status(api_client, make_asset):
    make_asset(asset_tag="LAPTOP-001", status=Asset.Status.AVAILABLE)
    make_asset(asset_tag="LAPTOP-002", status=Asset.Status.MAINTENANCE)

    response = api_client.get("/api/v1/assets/?status=MAINTENANCE")

    assert response.status_code == 200
    tags = [a["asset_tag"] for a in response.data["results"]]
    assert tags == ["LAPTOP-002"]


@pytest.mark.django_db
def test_filter_assets_by_category(api_client, make_asset):
    make_asset(asset_tag="LAPTOP-001", category=Asset.Category.LAPTOP)
    make_asset(asset_tag="CAMERA-001", category=Asset.Category.CAMERA)

    response = api_client.get("/api/v1/assets/?category=CAMERA")

    assert response.status_code == 200
    tags = [a["asset_tag"] for a in response.data["results"]]
    assert tags == ["CAMERA-001"]


@pytest.mark.django_db
def test_search_assets_by_name(api_client, make_asset):
    make_asset(asset_tag="LAPTOP-001", name="Dell XPS 15")
    make_asset(asset_tag="LAPTOP-002", name="MacBook Pro")

    response = api_client.get("/api/v1/assets/?search=MacBook")

    assert response.status_code == 200
    tags = [a["asset_tag"] for a in response.data["results"]]
    assert tags == ["LAPTOP-002"]


@pytest.mark.django_db
def test_search_assets_by_tag(api_client, make_asset):
    make_asset(asset_tag="CAMERA-777", name="Sony A7 III")
    make_asset(asset_tag="LAPTOP-002", name="MacBook Pro")

    response = api_client.get("/api/v1/assets/?search=CAMERA-777")

    assert response.status_code == 200
    tags = [a["asset_tag"] for a in response.data["results"]]
    assert tags == ["CAMERA-777"]


# ---- Detail / current_holder -------------------------------------------


@pytest.mark.django_db
def test_asset_detail_no_current_holder(api_client, make_asset):
    asset = make_asset()

    response = api_client.get(f"/api/v1/assets/{asset.id}/")

    assert response.status_code == 200
    assert response.data["current_holder"] is None


@pytest.mark.django_db
def test_asset_detail_with_current_holder(api_client, make_asset, make_employee):
    asset = make_asset(status=Asset.Status.CHECKED_OUT)
    employee = make_employee()
    CheckOut.objects.create(
        asset=asset,
        employee=employee,
        due_at="2026-12-01T00:00:00Z",
        returned_at=None,
    )

    response = api_client.get(f"/api/v1/assets/{asset.id}/")

    assert response.status_code == 200
    assert response.data["current_holder"] == {
        "employee_code": "EMP001",
        "full_name": "Jane Doe",
    }


@pytest.mark.django_db
def test_asset_detail_returned_checkout_has_no_holder(
    api_client, make_asset, make_employee
):
    asset = make_asset(status=Asset.Status.AVAILABLE)
    employee = make_employee()
    CheckOut.objects.create(
        asset=asset,
        employee=employee,
        due_at="2026-01-01T00:00:00Z",
        returned_at="2026-01-05T00:00:00Z",  # already returned
    )

    response = api_client.get(f"/api/v1/assets/{asset.id}/")

    assert response.status_code == 200
    assert response.data["current_holder"] is None


@pytest.mark.django_db
def test_asset_detail_not_found(api_client):
    response = api_client.get("/api/v1/assets/99999/")

    assert response.status_code == 404