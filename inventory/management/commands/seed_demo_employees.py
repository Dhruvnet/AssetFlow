from django.core.management.base import BaseCommand

from inventory.models import Employee


class Command(BaseCommand):
    help = "Seed demo employees for local development and API testing."

    FIRST_NAMES = [
        "Alice",
        "Bob",
        "Carol",
        "David",
        "Emma",
        "Frank",
        "Grace",
        "Henry",
        "Ivy",
        "Jack",
        "Karen",
        "Leo",
        "Maya",
        "Noah",
        "Olivia",
        "Peter",
        "Quinn",
        "Rachel",
        "Sam",
        "Tina",
    ]

    LAST_NAMES = [
        "Johnson",
        "Smith",
        "Williams",
        "Brown",
        "Davis",
        "Miller",
        "Wilson",
        "Moore",
        "Taylor",
        "Anderson",
        "Thomas",
        "Jackson",
        "White",
        "Harris",
        "Martin",
        "Thompson",
        "Garcia",
        "Martinez",
        "Robinson",
        "Clark",
    ]

    EMPLOYEES_PER_RUN = 4

    def handle(self, *args, **options):
        existing_count = Employee.objects.count()

        for index in range(
            1,
            self.EMPLOYEES_PER_RUN + 1,
        ):
            employee_number = existing_count + index

            name_index = (
                employee_number - 1
            ) % len(self.FIRST_NAMES)

            full_name = (
                f"{self.FIRST_NAMES[name_index]} "
                f"{self.LAST_NAMES[name_index]}"
            )

            Employee.objects.create(
                employee_code=(
                    f"EMP{employee_number:03d}"
                ),
                full_name=full_name,
                email=(
                    f"employee{employee_number:03d}"
                    "@example.com"
                ),
                is_active=(
                    employee_number % 4 != 0
                ),
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Employee seed complete. "
                f"{self.EMPLOYEES_PER_RUN} new employees created."
            )
        )