from celery import shared_task
from django.utils import timezone

from inventory.models import CheckOut, OverdueNotice


@shared_task
def flag_overdue_checkouts():
    now = timezone.now()
    today = now.date()

    overdue_checkouts = CheckOut.objects.filter(
        returned_at__isnull=True,
        due_at__lt=now,
    )

    created_count = 0

    for checkout in overdue_checkouts:
        _, created = OverdueNotice.objects.get_or_create(
            checkout=checkout,
            notice_date=today,
        )

        if created:
            created_count += 1

    return created_count