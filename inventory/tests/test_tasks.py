from datetime import timedelta

import pytest
from django.utils import timezone

from inventory.models import Asset, Employee, CheckOut, OverdueNotice
from inventory.tasks import flag_overdue_checkouts


@pytest.mark.django_db
def test_flag_overdue_checkouts_is_idempotent():
    asset = Asset.objects.create(
        asset_tag="LAPTOP-100",
        name="ThinkPad",
        category=Asset.Category.LAPTOP,
        status=Asset.Status.CHECKED_OUT,
        purchase_date=timezone.now().date(),
    )
    employee = Employee.objects.create(
        employee_code="EMP100",
        full_name="Jane Doe",
        email="jane@example.com",
    )
    checkout = CheckOut.objects.create(
        asset=asset,
        employee=employee,
        due_at=timezone.now() - timedelta(days=2),  # overdue
    )

    flag_overdue_checkouts()
    flag_overdue_checkouts()  # run twice, same day

    notices = OverdueNotice.objects.filter(checkout=checkout)
    assert notices.count() == 1


@pytest.mark.django_db
def test_flag_overdue_checkouts_ignores_not_yet_due():
    asset = Asset.objects.create(
        asset_tag="LAPTOP-101",
        name="ThinkPad 2",
        category=Asset.Category.LAPTOP,
        status=Asset.Status.CHECKED_OUT,
        purchase_date=timezone.now().date(),
    )
    employee = Employee.objects.create(
        employee_code="EMP101",
        full_name="John Doe",
        email="john@example.com",
    )
    checkout = CheckOut.objects.create(
        asset=asset,
        employee=employee,
        due_at=timezone.now() + timedelta(days=5),  # not overdue
    )

    flag_overdue_checkouts()

    assert OverdueNotice.objects.filter(checkout=checkout).count() == 0


@pytest.mark.django_db
def test_flag_overdue_checkouts_ignores_returned():
    asset = Asset.objects.create(
        asset_tag="LAPTOP-102",
        name="ThinkPad 3",
        category=Asset.Category.LAPTOP,
        status=Asset.Status.AVAILABLE,
        purchase_date=timezone.now().date(),
    )
    employee = Employee.objects.create(
        employee_code="EMP102",
        full_name="Sam Doe",
        email="sam@example.com",
    )
    checkout = CheckOut.objects.create(
        asset=asset,
        employee=employee,
        due_at=timezone.now() - timedelta(days=2),
        returned_at=timezone.now() - timedelta(days=1),  # already returned
    )

    flag_overdue_checkouts()

    assert OverdueNotice.objects.filter(checkout=checkout).count() == 0