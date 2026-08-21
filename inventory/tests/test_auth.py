import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user(db):
    return User.objects.create_user(username="testuser", password="testpass123")


@pytest.mark.django_db
def test_valid_login_returns_tokens(api_client, user):
    response = api_client.post(
        "/api/v1/auth/login/",
        {"username": "testuser", "password": "testpass123"},
    )
    assert response.status_code == 200
    assert "access" in response.data
    assert "refresh" in response.data


@pytest.mark.django_db
def test_invalid_login_rejected(api_client, user):
    response = api_client.post(
        "/api/v1/auth/login/",
        {"username": "testuser", "password": "wrongpass"},
    )
    assert response.status_code == 401


@pytest.mark.django_db
def test_protected_endpoint_without_token_rejected(api_client):
    response = api_client.get("/api/v1/assets/")
    assert response.status_code == 401


@pytest.mark.django_db
def test_protected_endpoint_with_valid_token_works(api_client, user):
    login = api_client.post(
        "/api/v1/auth/login/",
        {"username": "testuser", "password": "testpass123"},
    )
    token = login.data["access"]

    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    response = api_client.get("/api/v1/assets/")
    assert response.status_code == 200