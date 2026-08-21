import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient


@pytest.fixture
def api_client(db):
    """
    An APIClient authenticated as a Django user via JWT.

    Every protected endpoint requires a Bearer token (Batch 21 / A3).
    Centralising this here means every test module gets an authenticated
    client for free, instead of each file defining its own unauthenticated
    APIClient() and silently getting 401s.
    """
    user = User.objects.create_user(username="testuser", password="testpass123")
    client = APIClient()
    client.force_authenticate(user=user)
    return client