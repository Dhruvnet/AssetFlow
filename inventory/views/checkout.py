from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from inventory.serializers import (
    CheckOutCreateSerializer,
    CheckOutSerializer,
)
from inventory.services.checkout import create_checkout


class CheckOutCreateView(APIView):
    """
    POST /api/v1/checkouts/

    Creates a checkout and marks the asset as CHECKED_OUT.
    """

    def post(self, request):
        serializer = CheckOutCreateSerializer(
            data=request.data
        )
        serializer.is_valid(raise_exception=True)

        checkout = create_checkout(
            **serializer.validated_data
        )

        return Response(
            {
                "message": "Asset checked out successfully.",
                "data": CheckOutSerializer(checkout).data,
            },
            status=status.HTTP_201_CREATED,
        )