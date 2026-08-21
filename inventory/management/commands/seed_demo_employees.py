from django.core.management.base import BaseCommand

from inventory.models import Employee


class Command(BaseCommand):
    help = "Seed demo employees for local development and API testing."

    EMPLOYEES = [
        {
            "employee_code": "EMP001",
            "full_name": "Alice Johnson",
            "email": "alice@example.com",
            "is_active": True,
        },
        {
            "employee_code": "EMP002",
            "full_name": "Bob Smith",
            "email": "bob@example.com",
            "is_active": True,
        },
        {
            "employee_code": "EMP003",
            "full_name": "Carol Williams",
            "email": "carol@example.com",
            "is_active": True,
        },
        {
            "employee_code": "EMP004",
            "full_name": "David Brown",
            "email": "david@example.com",
            "is_active": False,
        },
    ]

    def handle(self, *args, **options):
        created_count = 0
        existing_count = 0

        for employee_data in self.EMPLOYEES:
            _, created = Employee.objects.get_or_create(
                employee_code=employee_data["employee_code"],
                defaults=employee_data,
            )

            if created:
                created_count += 1
            else:
                existing_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                "Employee seed complete. "
                f"{created_count} new employees created, "
                f"{existing_count} already existed."
            )
        )