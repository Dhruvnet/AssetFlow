from django.urls import path

from inventory.views import (
    AssetDetailView,
    AssetListCreateView,
    CheckOutCreateView,
    CheckOutReturnView,
    EmployeeCheckOutHistoryView,
    EmployeeSummaryView,
    OverdueCheckOutReportView,
)

urlpatterns = [
    path("assets/",AssetListCreateView.as_view(),name="asset-list-create",),
    path("assets/<int:pk>/",AssetDetailView.as_view(),name="asset-detail",),
    path("checkouts/",CheckOutCreateView.as_view(),name="checkout-create",),
    path("checkouts/<int:checkout_id>/return/",CheckOutReturnView.as_view(),name="checkout-return",),
    path("employees/<str:employee_code>/summary/",EmployeeSummaryView.as_view(),name="employee-summary",),
    path("reports/overdue/",OverdueCheckOutReportView.as_view(),name="overdue-report",),
    path("employees/<str:employee_code>/checkouts/",EmployeeCheckOutHistoryView.as_view(),name="employee-checkout-history",),
]