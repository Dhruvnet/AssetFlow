from django.db import connection
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthCheckView(APIView):
    """Unauthenticated health check reporting database connectivity."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            return Response(
                {"status": "healthy", "database": "connected"},
                status=200,
            )
        except Exception:
            return Response(
                {"status": "unhealthy", "database": "disconnected"},
                status=503,
            )