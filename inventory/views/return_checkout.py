from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from inventory.serializers import (
    CheckOutReturnSerializer,
    CheckOutSerializer,
)
from inventory.services.return_checkout import return_checkout


class CheckOutReturnView(APIView):
    """
    POST /api/v1/checkouts/{id}/return/

    Returns an asset and updates its status.
    """

    def post(self, request, checkout_id):
        serializer = CheckOutReturnSerializer(
            data=request.data
        )

        serializer.is_valid(
            raise_exception=True
        )

        checkout = return_checkout(
            checkout_id=checkout_id,
            **serializer.validated_data,
        )

        return Response(
            {
                "message": "Asset returned successfully.",
                "data": CheckOutSerializer(checkout).data,
            },
            status=status.HTTP_200_OK,
        )