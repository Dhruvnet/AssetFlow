from rest_framework.response import Response
from rest_framework.views import APIView

from inventory.serializers import (
    EmployeeCheckOutHistorySerializer,
    EmployeeSummarySerializer,
    OverdueCheckOutSerializer,
)
from inventory.services.reporting import (
    get_employee_checkouts,
    get_employee_summary,
    get_overdue_checkouts,
)


class EmployeeSummaryView(APIView):
    """
    GET /api/v1/employees/{employee_code}/summary/
    """

    def get(self, request, employee_code):
        summary = get_employee_summary(
            employee_code=employee_code,
        )

        serializer = EmployeeSummarySerializer(
            summary,
        )

        return Response(serializer.data)


class OverdueCheckOutReportView(APIView):
    """
    GET /api/v1/reports/overdue/
    """

    def get(self, request):
        checkouts = get_overdue_checkouts()

        serializer = OverdueCheckOutSerializer(
            checkouts,
            many=True,
        )

        return Response(serializer.data)
    
    
class EmployeeCheckOutHistoryView(APIView):
    """
    GET /api/v1/employees/{employee_code}/checkouts/

    Returns the employee's current and past
    checkout history.
    """

    def get(self, request, employee_code):
        checkout_history = get_employee_checkouts(
            employee_code=employee_code,
        )

        serializer = EmployeeCheckOutHistorySerializer(
            checkout_history,
        )

        return Response(serializer.data)